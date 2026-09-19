/// Application configuration loaded from environment variables.
#[derive(Clone, Debug)]
pub struct Config {
    pub host: String,
    pub port: u16,
    pub database_url: String,
    pub opencode_api_key: String,
    pub opencode_base_url: String,
    pub llm_model: String,
    pub latex_engine: String,
}

impl Config {
    /// Load configuration from environment variables (via dotenvy).
    pub fn from_env() -> anyhow::Result<Self> {
        // Load .env from project root (web/../.env)
        let env_path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap_or(std::path::Path::new("."))
            .join(".env");
        let _ = dotenvy::from_path(&env_path);

        Ok(Self {
            host: std::env::var("HOST").unwrap_or_else(|_| "127.0.0.1".into()),
            port: std::env::var("PORT")
                .unwrap_or_else(|_| "3000".into())
                .parse()?,
            database_url: std::env::var("DATABASE_URL")
                .unwrap_or_else(|_| "sqlite:careerhelper.db?mode=rwc".into()),
            opencode_api_key: std::env::var("OPENCODE_GO_API_KEY")?,
            opencode_base_url: std::env::var("OPENCODE_GO_BASE_URL")
                .unwrap_or_else(|_| "https://opencode.ai/zen/go/v1".into()),
            llm_model: std::env::var("LLM_MODEL")
                .unwrap_or_else(|_| "kimi-k3".into()),
            latex_engine: std::env::var("LATEX_ENGINE")
                .unwrap_or_else(|_| "pdflatex".into()),
        })
    }

    pub fn bind_addr(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}
