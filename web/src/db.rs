use sqlx::sqlite::SqlitePoolOptions;

/// Initialize the database connection pool and run pending migrations.
pub async fn init(database_url: &str) -> anyhow::Result<sqlx::SqlitePool> {
    let pool = SqlitePoolOptions::new()
        .max_connections(5)
        .connect(database_url)
        .await?;

    sqlx::migrate!("./migrations").run(&pool).await?;

    tracing::info!("Database initialized and migrations applied");
    Ok(pool)
}
