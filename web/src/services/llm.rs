/// LLM client service.
/// Calls OpenAI-compatible APIs (OpenCode Zen Go, OpenAI, etc.).

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessage>,
    temperature: f64,
    max_tokens: u32,
}

#[derive(Debug, Deserialize)]
struct ChatChoice {
    message: ChatMessageResponse,
    finish_reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ChatMessageResponse {
    content: String,
}

#[derive(Debug, Deserialize)]
struct Usage {
    prompt_tokens: u32,
    completion_tokens: u32,
    total_tokens: u32,
}

#[derive(Debug, Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
    usage: Option<Usage>,
}

#[derive(Debug)]
pub struct LlmResponse {
    pub content: String,
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
}

/// Call the LLM with a system prompt and user message.
pub async fn chat(
    api_key: &str,
    base_url: &str,
    model: &str,
    system_prompt: &str,
    user_prompt: &str,
) -> anyhow::Result<LlmResponse> {
    let client = reqwest::Client::new();

    let request = ChatRequest {
        model: model.to_string(),
        messages: vec![
            ChatMessage {
                role: "system".into(),
                content: system_prompt.to_string(),
            },
            ChatMessage {
                role: "user".into(),
                content: user_prompt.to_string(),
            },
        ],
        temperature: 0.3,
        max_tokens: 8000,
    };

    let response = client
        .post(format!("{}/chat/completions", base_url.trim_end_matches('/')))
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&request)
        .send()
        .await?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(anyhow::anyhow!("LLM API error {}: {}", status, body));
    }

    let chat_response: ChatResponse = response.json().await?;
    let choice = chat_response.choices.into_iter().next()
        .ok_or_else(|| anyhow::anyhow!("No choices in response"))?;

    let usage = chat_response.usage.unwrap_or(Usage {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
    });

    Ok(LlmResponse {
        content: choice.message.content,
        prompt_tokens: usage.prompt_tokens,
        completion_tokens: usage.completion_tokens,
    })
}
