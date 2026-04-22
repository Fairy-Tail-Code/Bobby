import uvicorn

from knowledge_server.app import create_app
from knowledge_server.config import ServerConfig


def main() -> None:
    config = ServerConfig.from_env()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level=config.log_level)


if __name__ == "__main__":
    main()
