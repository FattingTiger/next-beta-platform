from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SERVER_ROOT / "tests" / "e2e" / "native_restore_drill.sh"
ACCEPTANCE = SERVER_ROOT / "tests" / "e2e" / "THIRD_ROUND_ACCEPTANCE.md"


def logical_shell_commands(document: str) -> list[str]:
    commands: list[str] = []
    current: list[str] = []
    for raw_line in document.splitlines():
        stripped = raw_line.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        current.append(stripped.removesuffix("\\").strip())
        if not raw_line.rstrip().endswith("\\"):
            commands.append(" ".join(current))
            current = []
    assert not current
    return commands


def test_connected_postgres_tools_pin_the_native_maintenance_identity() -> None:
    commands = logical_shell_commands(SCRIPT.read_text(encoding="utf-8"))
    connected = [
        command
        for command in commands
        if 'runuser -u beta-pg -- "$PG_BIN/' in command and 'pg_restore" --list' not in command
    ]

    assert connected
    for command in connected:
        assert '--host="$PG_SOCKET"' in command
        assert '--port="$PG_PORT"' in command
        assert "--username=beta-pg" in command
        assert "--no-password" in command


def test_production_identity_contract_matches_real_psql_boolean_text() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "current_user || '|' || current_setting('data_directory')" in script
    assert "current_setting('port') || '|' || pg_is_in_recovery()" in script
    assert '"beta-pg|$PG_DATA|$PG_PORT|false"' in script
    assert "pg_get_userbyid(datdba)" in script
    assert '"$SOURCE_DATABASE|beta_center|false"' in script
    assert "rolsuper || '|' || rolcreatedb || '|' || rolcreaterole || '|' || rolreplication" in script
    assert "'beta_center|false|false|false|false'" in script


def test_only_generated_scratch_database_is_created_restored_or_dropped() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    commands = logical_shell_commands(script)
    createdb = [command for command in commands if '"$PG_BIN/createdb"' in command]
    dropdb = [command for command in commands if '"$PG_BIN/dropdb"' in command]
    restores = [
        command for command in commands if '"$PG_BIN/pg_restore"' in command and "--list" not in command
    ]

    assert 'scratch_database="beta_restore_drill_${stamp//[^0-9]/}_$$"' in script
    assert "^beta_restore_drill_[0-9]{14}_[0-9]+$" in script
    assert '[[ "$scratch_database" != "$SOURCE_DATABASE" ]]' in script
    assert "stale scratch database(s) require manual inspection" in script
    assert len(createdb) == 1 and '"$scratch_database"' in createdb[0]
    assert len(dropdb) == 2 and all('"$scratch_database"' in command for command in dropdb)
    assert len(restores) == 1
    assert '--dbname="$scratch_database"' in restores[0]
    assert "--single-transaction" in restores[0]
    assert "--no-owner" in restores[0]
    assert "--role=beta_center" in restores[0]


def test_source_and_restored_evidence_matches_before_completion() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'table_counts "$SOURCE_DATABASE" >"$destination/source.counts"' in script
    assert 'table_counts "$scratch_database" >"$destination/restored.counts"' in script
    assert 'cmp -s "$destination/source.counts" "$destination/restored.counts"' in script
    assert '>"$destination/source-alembic-version"' in script
    assert '>"$destination/restored-alembic-version"' in script
    assert 'cmp -s "$destination/source-alembic-version" "$destination/restored-alembic-version"' in script

    final_cleanup = script.index("# Completion means the scratch database is already gone.")
    drop = script.index('"$PG_BIN/dropdb"', final_cleanup)
    clear_flag = script.index("scratch_created=false", drop)
    complete = script.index('>"$destination/complete"', clear_flag)
    assert final_cleanup < drop < clear_flag < complete


def test_drill_has_no_storage_or_host_network_mutation_surface() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    acceptance = ACCEPTANCE.read_text(encoding="utf-8")

    for forbidden in (
        "sing-box",
        "iptables",
        "ip6tables",
        "firewall-cmd",
        "nft ",
        "ip route",
        "ip rule",
        "route ",
        ":443",
        "storage",
    ):
        assert forbidden not in script
    assert "systemctl stop" not in script
    assert "systemctl start" not in script
    assert "它不读取或写入 storage" in acceptance
    assert "这只证明数据库备份可恢复，不证明 APK/截图 storage 的灾备" in acceptance
