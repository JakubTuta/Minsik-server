import fastapi
import fastapi.middleware.cors
import app.config

settings = app.config.settings


def setup_cors(app: fastapi.FastAPI):
    app.add_middleware(
        fastapi.middleware.cors.CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods.split(","),
        allow_headers=settings.cors_allow_headers.split(","),
    )
