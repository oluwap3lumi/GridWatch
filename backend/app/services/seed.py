"""Synthetic seed command: pure generation followed by an atomic repository transaction."""

import json
from dataclasses import asdict

from data.generator.config import GeneratorConfig
from data.generator.dataset import generate_dataset

from app.core.settings import Settings
from app.db.session import make_engine, session_factory
from app.repositories.seed import replace_demo_data


def main() -> None:
    """Print actual loaded counts and source/database hashes, never credentials."""
    dataset = generate_dataset(GeneratorConfig.from_env())
    engine = make_engine(Settings.from_env())
    try:
        with session_factory(engine)() as session, session.begin():
            result = replace_demo_data(session, dataset)
        print(json.dumps(asdict(result), sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
