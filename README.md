# Minsik Server

The backend for [Minsik](https://minsik.jtuta.cloud) — a book discovery and tracking app.

[Live App](https://minsik.jtuta.cloud) · [Web Repo](https://github.com/JakubTuta/Minsik-web) · [API Docs](https://minsik.api.jtuta.cloud/docs) · License: MIT

---

Minsik lets you track what you're reading, rate books across nine dimensions, write reviews, and explore authors and series. This repository is the backend: a set of microservices behind a single REST gateway. The web frontend lives in [Minsik-web](https://github.com/JakubTuta/Minsik-web).

## ✨ Features

- **Full-text search** across books, authors, and series with type filters — powered by Elasticsearch with BM25 scoring, popularity and recency signals
- **9-dimension ratings** — an overall star rating plus eight sub-dimensions: Pacing, Emotional Impact, Intellectual Depth, Writing Quality, Rereadability, Readability, Plot Complexity, and Humor
- **Bookshelves** with four statuses (Want to Read, Reading, Read, Abandoned), favourites, and comments with optional spoiler flag
- **Continuous ingestion** from Open Library (bulk dump + incremental API) and Google Books, with automatic description enrichment and quality-based cleanup
- **JWT authentication** with short-lived access tokens and rotating refresh tokens

## 🛠 Tech Stack

|                         |                         |
| ----------------------- | ----------------------- |
| Gateway                 | FastAPI + uvicorn       |
| Internal communication  | gRPC + Protocol Buffers |
| Database                | PostgreSQL 15           |
| Search                  | Elasticsearch 8         |
| Cache / Background jobs | Redis 7 + RQ            |
| Auth                    | JWT (HS256)             |
| Migrations              | Alembic                 |

## 🏗 Architecture

The gateway is the only publicly exposed service. All internal services communicate exclusively over gRPC. Proto definitions live in `proto/` and are compiled into each service container at startup.

| Service             | Port         | Role                                                   |
| ------------------- | ------------ | ------------------------------------------------------ |
| `gateway-service`   | 8040 (HTTP)  | Public REST API, routes requests to internal services  |
| `auth-service`      | 50051 (gRPC) | Registration, login, JWT issuance and validation       |
| `books-service`     | 50055 (gRPC) | Book, author, and series catalog; Elasticsearch search |
| `user-data-service` | 50053 (gRPC) | Bookshelves, ratings, favourites, comments             |
| `ingestion-service` | 50054 (gRPC) | Data import from Open Library and Google Books         |
| `rq-worker`         | —            | Background job worker for the ingestion queue          |

Infrastructure: PostgreSQL 15, Redis 7, Elasticsearch 8.

## 🚀 Getting Started

```bash
git clone https://github.com/JakubTuta/Minsik-server
cd Minsik-server
cp .env.example .env
docker compose up -d --build
```

The API will be available at `http://localhost:8040`. See the [Environment Variables](#-environment-variables) section below before running in production.

## ⚙️ Environment Variables

The full reference is in `.env.example` — every variable is commented. Below is what matters most.

### Required for production

| Variable               | Notes                                                                 |
| ---------------------- | --------------------------------------------------------------------- |
| `DB_PASSWORD`          | Replace the default with a strong password                            |
| `REDIS_PASSWORD`       | Replace the default with a strong password                            |
| `JWT_SECRET_KEY`       | Generate with `openssl rand -hex 32`                                  |
| `GOOGLE_BOOKS_API_KEY` | Obtain from [Google Cloud Console](https://console.cloud.google.com/) |
| `ENV`                  | Set to `production`                                                   |
| `DEBUG`                | Set to `false`                                                        |
| `LOG_LEVEL`            | Set to `ERROR`                                                        |

### Notable optional settings

- **Cache TTLs** — how long book, author, and search results are cached in Redis (`CACHE_*_TTL`)
- **Rate limiting** — requests per minute for regular and admin endpoints (`RATE_LIMIT_*`)
- **Elasticsearch reindex** — how often the search index is rebuilt (`ES_REINDEX_INTERVAL_HOURS`)
- **Continuous ingestion** — toggle and configure polling intervals and batch sizes for Open Library and Google Books (`CONTINUOUS_*`)
- **Data cleanup** — minimum quality score and author book count thresholds for automatic pruning (`CLEANUP_*`)

## 📖 API Documentation

Interactive Swagger UI with all request/response schemas:
**[minsik.api.jtuta.cloud/docs](https://minsik.api.jtuta.cloud/docs)**

## ⚖️ License

Distributed under the MIT License. Copyright © 2025 Jakub Tutka.
