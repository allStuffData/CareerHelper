use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct Template {
    pub id: String,             // UUID
    pub name: String,
    pub description: String,
    pub is_predefined: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, FromRow, Serialize, Deserialize)]
pub struct TemplateVersion {
    pub id: String,             // UUID
    pub template_id: String,    // FK → templates.id
    pub latex_content: String,
    pub version_number: i32,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}
