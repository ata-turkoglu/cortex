import asyncio

from app.main import app


def test_lifespan_closes_broker_after_shutdown(monkeypatch):
    from app.workers import broker as broker_module

    closed = []
    monkeypatch.setattr(broker_module.broker, "close", lambda: closed.append(True))

    async def exercise_lifespan():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(exercise_lifespan())
    assert closed == [True]
