from skeinrank_server import cli


def test_cli_invokes_uvicorn(monkeypatch):
    called = {}

    def fake_run(app, *, host, port, reload, log_level):
        called["app"] = app
        called["host"] = host
        called["port"] = port
        called["reload"] = reload
        called["log_level"] = log_level

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    rc = cli.main(
        ["--host", "127.0.0.1", "--port", "9000", "--reload", "--log-level", "debug"]
    )

    assert rc == 0
    assert called == {
        "app": "skeinrank_server.main:app",
        "host": "127.0.0.1",
        "port": 9000,
        "reload": True,
        "log_level": "debug",
    }
