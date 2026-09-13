"""Migration ordering and idempotency contract tests."""



from app.core.migrations import MIGRATION_FILES, migrations_dir, split_sql_statements


def test_migration_files_exist_in_order():
    base = migrations_dir()
    for name in MIGRATION_FILES:
        path = base / name
        assert path.is_file(), f"Missing migration: {name}"


def test_no_duplicate_migration_prefixes():
    prefixes = [name.split("_", 1)[0] for name in MIGRATION_FILES]
    assert prefixes == sorted(prefixes, key=lambda p: int(p))
    assert len(prefixes) == len(set(prefixes))


def test_no_conflicting_0002_files_remain():
    files = list(migrations_dir().glob("0002_*.sql"))
    assert len(files) == 1
    assert files[0].name == "0002_agent1_discovery.sql"


def test_split_sql_statements_skips_comments():
    sql = """
    -- comment
    CREATE TABLE IF NOT EXISTS foo (id INT);
    INSERT INTO foo VALUES (1);
    """
    statements = split_sql_statements(sql)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE")
