use askama::Template;
use axum::{response::Html, response::IntoResponse, http::StatusCode};

#[derive(Template)]
#[template(path = "index.html")]
struct IndexTemplate {
    title: String,
}

pub async fn index() -> impl IntoResponse {
    let tmpl = IndexTemplate {
        title: "CareerHelper — ATS Optimizer".into(),
    };
    match tmpl.render() {
        Ok(html) => Html(html).into_response(),
        Err(e) => {
            tracing::error!("Template render error: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, "Template error").into_response()
        }
    }
}

pub async fn health() -> impl IntoResponse {
    let pdflatex_ok = which::which("pdflatex").is_ok();
    let status = if pdflatex_ok { "ok" } else { "degraded: pdflatex not found" };
    axum::Json(serde_json::json!({
        "status": status,
        "pdflatex": pdflatex_ok,
    }))
}
