"""Import history, expiring staged rows, durable jobs, undo journal and asset identity."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add import foundations without rewriting existing asset values."""
    op.execute(
        """
        CREATE TABLE import_batches (
        id UUID NOT NULL,
        filename VARCHAR(512) NOT NULL,
        format VARCHAR(16),
        layer_type VARCHAR(16) NOT NULL,
        status VARCHAR(16) DEFAULT 'uploaded' NOT NULL,
        row_counts JSONB DEFAULT jsonb_build_object(
        'total',0,'valid',0,'invalid',0,'inserted',0,'updated',0) NOT NULL,
        detected_columns JSONB DEFAULT '[]'::jsonb NOT NULL,
        column_mapping JSONB DEFAULT '{}'::jsonb NOT NULL,
        crs_detected VARCHAR(4096),
        crs_selected VARCHAR(4096),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        error_report JSONB DEFAULT '{}'::jsonb NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_import_batches_format CHECK (format IN ('csv','shapefile','geojson')),
        CONSTRAINT ck_import_batches_layer CHECK (layer_type IN
        ('transformer','pole','feeder_line')),
        CONSTRAINT ck_import_batches_status CHECK (status IN
        ('uploaded','validated','imported','failed','rolled_back'))
        )
        """
    )
    op.execute("CREATE INDEX ix_import_batches_created_at ON import_batches (created_at)")
    op.execute("CREATE INDEX ix_import_batches_expires_at ON import_batches (expires_at)")
    op.execute(
        """
        CREATE TABLE import_jobs (
        id UUID NOT NULL,
        batch_id UUID NOT NULL,
        operation VARCHAR(16) NOT NULL,
        status VARCHAR(16) DEFAULT 'queued' NOT NULL,
        processed INTEGER DEFAULT '0' NOT NULL,
        total INTEGER DEFAULT '0' NOT NULL,
        attempts INTEGER DEFAULT '0' NOT NULL,
        lease_token UUID,
        lease_until TIMESTAMP WITH TIME ZONE,
        options JSONB DEFAULT '{}'::jsonb NOT NULL,
        error_code VARCHAR(64),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT ck_import_jobs_operation CHECK (operation IN
        ('inspect','validate','commit','rollback','rescore','cleanup')),
        CONSTRAINT ck_import_jobs_status CHECK (status IN
        ('queued','running','completed','failed')),
        CONSTRAINT ck_import_jobs_progress CHECK (processed >= 0 AND total >= 0 AND processed <=
        total AND attempts >= 0),
        FOREIGN KEY(batch_id) REFERENCES import_batches (id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_import_jobs_batch_id ON import_jobs (batch_id)")
    op.execute("CREATE INDEX ix_import_jobs_queue ON import_jobs (status, created_at)")
    op.execute(
        """
        CREATE TABLE import_rows (
        batch_id UUID NOT NULL,
        row_number INTEGER NOT NULL,
        source JSONB NOT NULL,
        normalized JSONB,
        geom geometry(GEOMETRY,4326),
        valid BOOLEAN DEFAULT false NOT NULL,
        errors JSONB DEFAULT '[]'::jsonb NOT NULL,
        warnings JSONB DEFAULT '[]'::jsonb NOT NULL,
        PRIMARY KEY (batch_id, row_number),
        CONSTRAINT ck_import_rows_number CHECK (row_number > 0),
        FOREIGN KEY(batch_id) REFERENCES import_batches (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE import_changes (
        batch_id UUID NOT NULL,
        asset_id BIGINT NOT NULL,
        operation VARCHAR(16) NOT NULL,
        before JSONB,
        after_revision BIGINT NOT NULL,
        PRIMARY KEY (batch_id, asset_id),
        CONSTRAINT ck_import_changes_operation CHECK (operation IN ('insert','update')),
        CONSTRAINT ck_import_changes_revision CHECK (after_revision > 0),
        FOREIGN KEY(batch_id) REFERENCES import_batches (id)
        )
        """
    )
    op.create_check_constraint(
        "ck_import_changes_before",
        "import_changes",
        "(operation = 'insert' AND before IS NULL) OR "
        "(operation = 'update' AND before IS NOT NULL)",
    )
    op.execute("CREATE SEQUENCE asset_id_seq OWNED BY assets.id")
    op.execute(
        "SELECT setval('asset_id_seq', COALESCE((SELECT max(id) FROM assets), 0) + 1, false)"
    )
    op.alter_column("assets", "id", server_default=sa.text("nextval('asset_id_seq'::regclass)"))
    for name in ("external_id", "external_feeder_id", "external_pole_id"):
        op.add_column("assets", sa.Column(name, sa.String(255)))
    op.add_column(
        "assets",
        sa.Column(
            "pole_id", sa.BigInteger(), sa.ForeignKey("assets.id", name="assets_pole_id_fkey")
        ),
    )
    for name in ("batch_id", "last_batch_id"):
        op.add_column(
            "assets",
            sa.Column(
                name, sa.Uuid(), sa.ForeignKey("import_batches.id", name=f"assets_{name}_fkey")
            ),
        )
    op.add_column(
        "assets", sa.Column("revision", sa.BigInteger(), server_default="0", nullable=False)
    )
    for name in ("pole_id", "batch_id", "last_batch_id"):
        op.create_index(f"ix_assets_{name}", "assets", [name])
    op.create_index("ix_assets_external_id", "assets", ["type", "external_id"], unique=True)
    op.create_check_constraint("ck_assets_revision", "assets", "revision >= 0")
    op.create_check_constraint(
        "ck_assets_external_id", "assets", "external_id IS NULL OR length(btrim(external_id)) > 0"
    )
    for name in (
        "install_date",
        "capacity_kva",
        "load_factor",
        "material",
        "vegetation_index",
        "last_maintenance_date",
    ):
        op.alter_column("assets", name, nullable=True)
    op.drop_constraint("ck_assets_geometry_and_parent", "assets", type_="check")
    op.create_check_constraint(
        "ck_assets_geometry_and_parent",
        "assets",
        "(type = 'feeder' AND GeometryType(geom) IN ('LINESTRING','MULTILINESTRING') "
        "AND feeder_id IS NULL AND pole_id IS NULL) OR "
        "(type IN ('transformer', 'pole') AND GeometryType(geom) = 'POINT' "
        "AND (type = 'transformer' OR pole_id IS NULL))",
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION guard_asset_feeder() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF NEW.feeder_id IS NOT NULL THEN
        PERFORM id FROM assets WHERE id = NEW.feeder_id AND type = 'feeder' FOR SHARE;
        IF NOT FOUND THEN
        RAISE EXCEPTION 'invalid feeder reference' USING ERRCODE = '23514';
        END IF;
        END IF;
        IF NEW.pole_id IS NOT NULL THEN
        PERFORM id FROM assets WHERE id = NEW.pole_id AND type = 'pole' FOR SHARE;
        IF NOT FOUND THEN
        RAISE EXCEPTION 'invalid pole reference' USING ERRCODE = '23514';
        END IF;
        END IF;
        IF TG_OP = 'UPDATE' THEN
        IF OLD.type = 'feeder' AND NEW.type <> 'feeder'
        AND EXISTS (SELECT 1 FROM assets WHERE feeder_id = OLD.id) THEN
        RAISE EXCEPTION 'referenced feeder type change' USING ERRCODE = '23514';
        END IF;
        IF OLD.type = 'pole' AND NEW.type <> 'pole'
        AND EXISTS (SELECT 1 FROM assets WHERE pole_id = OLD.id) THEN
        RAISE EXCEPTION 'referenced pole type change' USING ERRCODE = '23514';
        END IF;
        NEW.revision := OLD.revision + 1;
        END IF;
        RETURN NEW;
        END $$
        """)
    op.execute("DROP TRIGGER assets_feeder_guard ON assets")
    op.execute(
        """
        CREATE TRIGGER assets_feeder_guard BEFORE INSERT OR UPDATE ON assets FOR EACH ROW
        EXECUTE FUNCTION guard_asset_feeder()
        """
    )


def downgrade() -> None:
    """Refuse lossy downgrades; existing synthetic seed rows remain compatible."""
    op.execute("""
        DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM import_batches) OR EXISTS (
        SELECT 1 FROM assets WHERE external_id IS NOT NULL OR pole_id IS NOT NULL
        OR install_date IS NULL OR capacity_kva IS NULL OR load_factor IS NULL
        OR material IS NULL OR vegetation_index IS NULL OR last_maintenance_date IS NULL
        OR GeometryType(geom) = 'MULTILINESTRING'
        OR (type <> 'feeder' AND feeder_id IS NULL)
        ) THEN
        RAISE EXCEPTION 'M8 data prevents lossless downgrade';
        END IF;
        END $$
        """)
    op.execute("DROP TRIGGER assets_feeder_guard ON assets")
    op.execute("""
        CREATE OR REPLACE FUNCTION guard_asset_feeder() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF NEW.feeder_id IS NOT NULL THEN
        PERFORM id FROM assets WHERE id = NEW.feeder_id AND type = 'feeder' FOR SHARE;
        IF NOT FOUND THEN
        RAISE EXCEPTION 'feeder_id must reference a feeder' USING ERRCODE = '23514';
        END IF;
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.type = 'feeder' AND NEW.type <> 'feeder'
        AND EXISTS (SELECT 1 FROM assets WHERE feeder_id = OLD.id) THEN
        RAISE EXCEPTION 'cannot change the type of a referenced feeder' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
        END $$
        """)
    op.execute(
        """
        CREATE TRIGGER assets_feeder_guard BEFORE INSERT OR UPDATE OF type, feeder_id ON assets
        FOR EACH ROW EXECUTE FUNCTION guard_asset_feeder()
        """
    )
    op.drop_constraint("ck_assets_geometry_and_parent", "assets", type_="check")
    op.create_check_constraint(
        "ck_assets_geometry_and_parent",
        "assets",
        "(type = 'feeder' AND GeometryType(geom) = 'LINESTRING' AND feeder_id IS NULL) OR "
        "(type IN ('transformer', 'pole') AND GeometryType(geom) = 'POINT' "
        "AND feeder_id IS NOT NULL)",
    )
    for name in (
        "install_date",
        "capacity_kva",
        "load_factor",
        "material",
        "vegetation_index",
        "last_maintenance_date",
    ):
        op.alter_column("assets", name, nullable=False)
    for name in ("ck_assets_revision", "ck_assets_external_id"):
        op.drop_constraint(name, "assets", type_="check")
    for name in ("pole_id", "batch_id", "last_batch_id", "external_id"):
        op.drop_index(f"ix_assets_{name}", table_name="assets")
    for name in ("pole_id", "batch_id", "last_batch_id"):
        op.drop_constraint(f"assets_{name}_fkey", "assets", type_="foreignkey")
    for name in (
        "external_id",
        "external_feeder_id",
        "external_pole_id",
        "pole_id",
        "batch_id",
        "last_batch_id",
        "revision",
    ):
        op.drop_column("assets", name)
    op.alter_column("assets", "id", server_default=None)
    op.execute("DROP SEQUENCE asset_id_seq")
    for name in ("import_changes", "import_rows", "import_jobs", "import_batches"):
        op.drop_table(name)
