use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct Generation {
    pub id: String,             // UUID
    pub template_version_id: String,
    pub company: String,
    pub role: String,
    pub jd_text: String,
    pub llm_prompt: String,
    pub llm_response: String,
    pub tex_content: String,
    pub pdf_path: Option<String>,
    pub prompt_tokens: Option<i64>,
    pub completion_tokens: Option<i64>,
    pub created_at: DateTime<Utc>,
}
