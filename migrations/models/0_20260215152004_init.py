from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "telegram_id" BIGINT NOT NULL UNIQUE,
    "name" VARCHAR(100) NOT NULL,
    "username" VARCHAR(235)
);
CREATE TABLE IF NOT EXISTS "site" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL UNIQUE,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "productgroup" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "is_active" BOOL NOT NULL DEFAULT False,
    "last_check" TIMESTAMPTZ,
    "site_id" INT NOT NULL REFERENCES "site" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "productlink" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "companyName" VARCHAR(255),
    "productName" VARCHAR(255),
    "url" VARCHAR(500) NOT NULL,
    "last_price" DOUBLE PRECISION,
    "last_check" TIMESTAMPTZ,
    "group_id" INT NOT NULL REFERENCES "productgroup" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_productlink_url_518538" UNIQUE ("url", "group_id")
);
CREATE TABLE IF NOT EXISTS "pricehistory" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "price" INT,
    "views" INT,
    "date" TIMESTAMPTZ NOT NULL,
    "product_link_id" INT NOT NULL REFERENCES "productlink" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
