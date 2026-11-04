mod config;
mod error;
mod service;
mod document;
mod format;

use config::Config;
use service::Service;
use document::{Document, DocumentFormat};
use format::FormatConverter;
use anyhow::Result;

fn main() -> Result<()> {
    env_logger::init();
    
    let config = Config::default();
    let mut service = Service::new(config);
    
    service.start()?;
    println!("Service started successfully");
    
    // Demonstrate document processing
    let doc = Document::new("Test".to_string(), "Content".to_string(), DocumentFormat::PlainText);
    println!("Document created: {}", doc.metadata.title);
    
    // Demonstrate format conversion
    let converter = FormatConverter::new();
    println!("Format converter initialized");
    
    service.stop()?;
    println!("Service stopped successfully");
    
    Ok(())
}
