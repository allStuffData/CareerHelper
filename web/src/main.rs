// Scaffolding phase: allow dead code until all modules are wired up.
#![allow(dead_code)]

use axum::{Router, routing::get};
use tower_http::{services::ServeDir, trace::TraceLayer, compression::CompressionLayer, cors::CorsLayer};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

mod config;
mod db;
mod models;
mod routes;
mod services;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // ── Logging ──────────────────────────────────────────────────────────
    tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "careerhelper=debug,tower_http=debug".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    // ── Config ───────────────────────────────────────────────────────────
    let _config = config::Config::from_env()?;
    tracing::info!("Starting CareerHelper on http://{}", _config.bind_addr());

    // ── Database ─────────────────────────────────────────────────────────
    db::init(&_config.database_url).await?;

    // ── Router ───────────────────────────────────────────────────────────
    let app = Router::new()
        .route("/", get(routes::pages::index))
        .route("/health", get(routes::pages::health))
        .nest_service("/static", ServeDir::new("static"))
        .layer(TraceLayer::new_for_http())
        .layer(CompressionLayer::new())
        .layer(CorsLayer::permissive());

    // ── Bind & serve ─────────────────────────────────────────────────────
    let listener = tokio::net::TcpListener::bind(_config.bind_addr()).await?;
    tracing::info!("Listening on {}", _config.bind_addr());
    axum::serve(listener, app).await?;

    Ok(())
}
