"""
Serviço de Inteligência de Mercado de Vagas (Market Intelligence)
Agregação estatística, normalização de termos, extração estruturada via IA, score de confiança.
"""

import json
import re
import time
import math
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI

# Dicionário de Sinônimos e Normalização Canônica
TECH_SYNONYMS = {
    # Linguagens
    "python": "Python",
    "py": "Python",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "golang": "Go",
    "go": "Go",
    "c#": "C#",
    "csharp": "C#",
    ".net": ".NET",
    "dotnet": ".NET",
    "java": "Java",
    "kotlin": "Kotlin",
    "ruby": "Ruby",
    "php": "PHP",
    "rust": "Rust",
    
    # Frontend
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "css3": "CSS",
    "html5": "HTML",

    # Backend & Frameworks
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "express": "Express.js",
    "expressjs": "Express.js",
    "nest": "NestJS",
    "nestjs": "NestJS",
    "spring": "Spring Boot",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    
    # Cloud & DevOps
    "aws": "Amazon Web Services (AWS)",
    "amazon web services": "Amazon Web Services (AWS)",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud Platform (GCP)",
    "google cloud": "Google Cloud Platform (GCP)",
    "docker": "Docker",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "terraform": "Terraform",
    "ci/cd": "CI/CD",
    "github actions": "GitHub Actions",
    
    # Banco de Dados
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "sqlite": "SQLite",
    "dynamodb": "DynamoDB",
    "elasticsearch": "Elasticsearch",

    # Data & AI
    "pandas": "Pandas",
    "numpy": "NumPy",
    "spark": "Apache Spark",
    "pyspark": "PySpark",
    "airflow": "Apache Airflow",
    "scikit-learn": "scikit-learn",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "sql": "SQL"
}

def normalize_tech(term: str) -> str:
    """Mapeia variações de escrita para o nome canônico único."""
    cleaned = term.strip().lower()
    return TECH_SYNONYMS.get(cleaned, term.strip())

def init_market_db(db_file: Path):
    """Inicializa as tabelas do módulo de inteligência de mercado."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Vagas brutas coletadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_raw_jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            description TEXT,
            location TEXT,
            modality TEXT,
            job_type TEXT,
            url TEXT,
            source TEXT,
            published_at TIMESTAMP,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Vagas extraídas/estruturadas por IA
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_extracted_jobs (
            id TEXT PRIMARY KEY,
            raw_job_id TEXT,
            is_relevant INTEGER,
            relevance_score REAL,
            role_level fontTEXT,
            exp_years_min INTEGER,
            exp_years_max INTEGER,
            req_techs TEXT, -- JSON array
            desirable_techs TEXT, -- JSON array
            certifications TEXT, -- JSON array
            soft_skills TEXT, -- JSON array
            salary_min REAL,
            salary_max REAL,
            currency TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (raw_job_id) REFERENCES market_raw_jobs(id)
        )
    ''')

    # Histórico de análises/relatórios de mercado
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_reports (
            id TEXT PRIMARY KEY,
            job_title TEXT,
            target_stack TEXT,
            seniority TEXT,
            location TEXT,
            time_window TEXT,
            total_jobs INTEGER,
            relevant_jobs fontINTEGER,
            confidence_score fontTEXT,
            report_data TEXT, -- JSON com todos os dados agregados
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def _generate_sample_jobs(job_title: str) -> List[Dict]:
    """Gera vagas mock diversificadas e realistas para amostragem."""
    base_jobs = [
        {"title": "Desenvolvedor Python / FastAPI Sênior", "company": "TechCorp Brasil", "description": "Buscamos dev Python com experiência em FastAPI, Docker e PostgreSQL. Requisitos: 4+ anos de experiência. Diferencial: AWS, Kubernetes. Atuação remota.", "location": "Remoto", "modality": "Remoto Nacional", "source": "LinkedIn"},
        {"title": "Engenheiro de Software Python Pleno", "company": "DataStream Solutions", "description": "Vaga para atuar em APIs Python com Django/FastAPI. Banco de dados Postgres e Redis. Experiência desejada: 3 anos. Certificação AWS é diferencial.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Senior Backend Engineer (Python / Go)", "company": "Fintech Global", "description": "Looking for Senior Python/Go Engineer. 5+ years experience. Microservices, Docker, Kubernetes, AWS. International remote position.", "location": "Remoto Internacional", "modality": "Remoto Internacional", "source": "Glassdoor"},
        {"title": "Desenvolvedor Backend Júnior (Python)", "company": "Startup X", "description": "Oportunidade Júnior! Conhecimentos em Python, SQL e Git. Vivência com Django ou FastAPI é um plus. 1 ano de experiência ou projetos relevantes.", "location": "Rio de Janeiro, RJ", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor Python / React Fullstack", "company": "SaaS Factory", "description": "Desenvolvimento com Python (FastAPI/Flask) no backend e React/TypeScript no frontend. 3 a 5 anos de exp. PostgreSQL e Tailwind CSS.", "location": "Remoto", "modality": "Remoto Nacional", "source": "LinkedIn"},
        {"title": "Engenheiro de Dados Python / Spark", "company": "BigData Inc", "description": "Pipelines de dados em Python, PySpark e Apache Airflow. AWS S3, Redshift. 3+ anos com data engineering.", "location": "Remoto", "modality": "Remoto Nacional", "source": "Programathor"},
        {"title": "Python Developer (FastAPI + AI)", "company": "AI Labs", "description": "Integração de LLMs, OpenAI API, FastAPI e LangChain. 2+ anos com Python. Conhecimento em Docker e suporte a modelos.", "location": "Remoto Internacional", "modality": "Remoto Internacional", "source": "LinkedIn"},
        {"title": "Dev Backend Python / Microserviços", "company": "E-Commerce Group", "description": "Arquitetura distribuída com Python, Kafka, Redis, PostgreSQL. Testes automatizados (pytest). 4 anos exp.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Desenvolvedor Frontend React / TypeScript", "company": "WebAgency", "description": "Frontend com React, TypeScript, Next.js e Tailwind. 2+ anos de experiência. Design system e testes com Jest/RTL.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Fullstack Developer (Python + React)", "company": "FinTech Startup", "description": "Fullstack com Python/FastAPI no backend e React/TypeScript no frontend. PostgreSQL, Docker, AWS. 3+ anos de experiência.", "location": "Remoto", "modality": "Remoto Nacional", "source": "GitHub Jobs"},
        {"title": "Engenheiro de Software Java / Spring Boot", "company": "BankTech", "description": "Desenvolvimento com Java 17, Spring Boot, Micronaut. Banco PostgreSQL, Kafka, Docker. 4+ anos de experiência em sistemas bancários.", "location": "São Paulo, SP", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor Node.js / TypeScript", "company": "Tech Solutions", "description": "Backend com Node.js, NestJS, TypeScript e MongoDB. API RESTful, testes com Jest, CI/CD com GitHub Actions. 2+ anos de experiência.", "location": "Florianópolis, SC", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "DevOps Engineer (AWS / Terraform)", "company": "Cloud Services", "description": "Infra como código com Terraform, CI/CD com GitHub Actions, Docker e Kubernetes no AWS. 3+ anos de experiência em DevOps.", "location": "Remoto", "modality": "Remoto Nacional", "source": "InfoJobs"},
        {"title": "Analista de Dados Python / SQL", "company": "DataInsights", "description": "Análise de dados com Python (Pandas, NumPy), SQL e Power BI. Modelos de machine learning com scikit-learn. 2 anos de experiência.", "location": "Belo Horizonte, MG", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Mobile React Native", "company": "App Factory", "description": "Desenvolvimento de apps mobile com React Native e TypeScript. Integração com APIs REST, SQLite e Firebase. 2+ anos de experiência.", "location": "Porto Alegre, RS", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "QA Engineer Python / Selenium", "company": "Quality First", "description": "Testes automatizados com Python, Selenium, Pytest e Cypress. CI/CD com Jenkins. 2+ anos de experiência em QA.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Catho"},
        {"title": "Product Designer / UI Engineer", "company": "Design Studio", "description": "Design de interfaces com Figma e desenvolvimento frontend com React, Tailwind CSS e Storybook. 3 anos de experiência.", "location": "Remoto", "modality": "Remoto Internacional", "source": "LinkedIn"},
        {"title": "Engenheiro de Machine Learning", "company": "AI Research Lab", "description": "Desenvolvimento de modelos de ML com Python, PyTorch e TensorFlow. Deploy de modelos com FastAPI e AWS SageMaker. 4+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Desenvolvedor C# / .NET", "company": "Enterprise Corp", "description": "Backend com C#, ASP.NET Core, Entity Framework e SQL Server. Arquitetura limpa e microserviços. 3+ anos de experiência.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor PHP / Laravel", "company": "WebDev Agency", "description": "Desenvolvimento web com PHP 8, Laravel, MySQL e Vue.js. 2+ anos de experiência. Conhecimento em AWS é diferencial.", "location": "Rio de Janeiro, RJ", "modality": "Remoto", "source": "InfoJobs"},
        {"title": "Software Engineer (Golang)", "company": "Tech Giants", "description": "Backend com Go, gRPC, PostgreSQL e Kafka. Sistemas distribuídos de alta performance. 3+ anos de experiência com Go.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Analista de Segurança da Informação", "company": "CyberSec", "description": "Análise de vulnerabilidades, pentest e segurança de aplicações. Conhecimento em OWASP, Burp Suite e Python. 3+ anos de experiência.", "location": "Brasília, DF", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor iOS / Swift", "company": "Mobile Apps", "description": "Desenvolvimento de apps iOS com Swift e SwiftUI. Integração com APIs REST e Firebase. 2+ anos de experiência.", "location": "Florianópolis, SC", "modality": "Híbrido", "source": "GitHub Jobs"},
        {"title": "Desenvolvedor Android / Kotlin", "company": "Android Studio", "description": "Desenvolvimento de apps Android com Kotlin e Jetpack Compose. MVVM, Room, Coroutines e Clean Architecture. 2+ anos de experiência.", "location": "São Paulo, SP", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Arquiteto de Software", "company": "Tech Leadership", "description": "Definição de arquitetura de sistemas distribuídos com microserviços, event-driven e cloud-native. 8+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Scrum Master / Tech Lead", "company": "Agile Corp", "description": "Liderança técnica de squad ágil com 8 desenvolvedores. Cerimônias Scrum, code review e mentoring. 5+ anos de experiência.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Estagiário de Desenvolvimento", "company": "Startup Junior", "description": "Estágio em desenvolvimento web com Python e JavaScript. Aprendizado de HTML, CSS, Git e frameworks modernos.", "location": "Remoto", "modality": "Remoto Nacional", "source": "Catho"},
        {"title": "Consultor Técnico de Vendas", "company": "SalesTech", "description": "Suporte técnico para vendas de soluções SaaS. Conhecimento em Python, APIs e cloud. 2+ anos de experiência.", "location": "São Paulo, SP", "modality": "Presencial", "source": "Indeed"},
        {"title": "Embedded Systems Engineer", "company": "IoT Solutions", "description": "Desenvolvimento de firmware em C/C++ para dispositivos IoT. Protocolos MQTT, ESP32 e Arduino. 3+ anos de experiência.", "location": "Campinas, SP", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Data Engineer (Spark / Airflow)", "company": "Data Platform", "description": "Construção de pipelines ETL com Apache Spark, Airflow e Python. AWS Redshift e S3. 4+ anos de experiência.", "location": "São Paulo, SP", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Desenvolvedor Unity 3D", "company": "Game Studio", "description": "Desenvolvimento de jogos 3D com Unity e C#. Shader programming e otimização de performance. 2+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Site Reliability Engineer", "company": "Cloud Infra", "description": "Monitoramento e confiabilidade de sistemas com Prometheus, Grafana e Kubernetes. Python e Go. 4+ anos de experiência.", "location": "Remoto", "modality": "Remoto Internacional", "source": "LinkedIn"},
        {"title": "Desenvolvedor Rust Systems", "company": "Systems Lab", "description": "Desenvolvimento de sistemas de alta performance com Rust. WASM, WebAssembly e integração com frontend. 3+ anos de experiência.", "location": "São Paulo, SP", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Technical Project Manager", "company": "PM Office", "description": "Gestão de projetos técnicos com metodologia ágil. Rastreamento de entregas, stakeholders e riscos. 5+ anos de experiência.", "location": "Rio de Janeiro, RJ", "modality": "Híbrido", "source": "Catho"},
        {"title": "Desenvolvedor .NET / Azure", "company": "Azure Partners", "description": "Desenvolvimento com .NET 6/7, Azure Functions, Blob Storage e SQL Server. 3+ anos de experiência.", "location": "Porto Alegre, RS", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Vue.js / Nuxt", "company": "Frontend Studio", "description": "Frontend com Vue.js 3, Nuxt 3, TypeScript e Pinia. SSR e otimização de performance. 2+ anos de experiência.", "location": "Remoto", "modality": "Remoto Nacional", "source": "LinkedIn"},
        {"title": "Engenheiro de Plataforma", "company": "Platform Team", "description": "Construção de plataformas internas com Kubernetes, Terraform, Istio e Go. 5+ anos de experiência em infraestrutura.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "UI/UX Designer + Frontend", "company": "Creative Tech", "description": "Design e desenvolvimento frontend com Figma, React e Tailwind CSS. Prototipagem e design systems. 3+ anos de experiência.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Desenvolvedor Backend Java", "company": "Java Solutions", "description": "Desenvolvimento com Java 21, Spring Boot 3, Micronaut e Quarkus. Maven, Gradle e testes com JUnit 5. 4+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Go / gRPC", "company": "Microservices Co", "description": "Microserviços com Go, gRPC, Protobuf e Kubernetes. Messaging com Kafka e RabbitMQ. 3+ anos de experiência.", "location": "Florianópolis, SC", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Analista de Segurança (Pentest)", "company": "Pentest Lab", "description": "Testes de penetração em aplicações web e infraestrutura. OWASP Top 10, Burp Suite, Metasploit. 3+ anos de experiência.", "location": "Brasília, DF", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor WordPress / PHP", "company": "Web Agency", "description": "Desenvolvimento de temas e plugins WordPress com PHP, JavaScript e MySQL. 2+ anos de experiência.", "location": "Remoto", "modality": "Remoto Nacional", "source": "InfoJobs"},
        {"title": "Engenheiro de Dados (Databricks)", "company": "BigData Corp", "description": "Plataforma Databricks com Spark, Delta Lake e dbt. SQL avançado e Python. 4+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Elixir / Phoenix", "company": "Functional Tech", "description": "Backend com Elixir, Phoenix Framework e PostgreSQL. Concorrência e sistemas em tempo real. 3+ anos de experiência.", "location": "São Paulo, SP", "modality": "Remoto", "source": "Glassdoor"},
        {"title": "Technical Writer / DevRel", "company": "Open Source Inc", "description": "Documentação técnica de APIs e SDKs. Python, JavaScript e conceitos de developer experience. 2+ anos de experiência.", "location": "Remoto", "modality": "Remoto Internacional", "source": "GitHub Jobs"},
        {"title": "Desenvolvedor Flutter / Dart", "company": "Mobile First", "description": "Apps multiplataforma com Flutter e Dart. Firebase, REST APIs e publicações na App Store e Play Store. 2+ anos.", "location": "Porto Alegre, RS", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Engenheiro de Cloud (AWS)", "company": "Cloud Ops", "description": "Infraestrutura AWS com CloudFormation, Lambda, ECS e EventBridge. Python e Terraform. 4+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Svelte / SvelteKit", "company": "Modern Web", "description": "Frontend com Svelte, SvelteKit e TypeScript. SSR, routing e state management. 1+ ano de experiência.", "location": "Remoto", "modality": "Remoto Nacional", "source": "GitHub Jobs"},
        {"title": "Tech Lead Python", "company": "Senior Engineering", "description": "Liderança técnica de squad Python com 10 engenheiros. Code review, arquitetura e mentoring. 7+ anos de experiência.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Backend PHP / Symfony", "company": "PHP Solutions", "description": "APIs com Symfony, Doctrine e PostgreSQL. Docker, CI/CD e testes com PHPUnit. 3+ anos de experiência.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Engenheiro de IA / NLP", "company": "AI Lab", "description": "Processamento de linguagem natural com Python, Hugging Face e transformers. Deploy de modelos com FastAPI. 3+ anos.", "location": "São Paulo, SP", "modality": "Remoto", "source": "Glassdoor"},
        {"title": "Desenvolvedor Blazor / .NET", "company": "Enterprise Web", "description": "Frontend com Blazor WebAssembly e backend .NET 8. SignalR para tempo real e Entity Framework Core. 2+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Go / Kubernetes", "company": "Cloud Native", "description": "Desenvolvimento de operators e controllers Kubernetes com Go. API de extensão e custom resources. 3+ anos.", "location": "Florianópolis, SC", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Cybersecurity Engineer", "company": "SecureNet", "description": "Segurança de aplicações e infraestrutura. SIEM, SOAR, incident response. Conhecimento em Python e Bash. 4+ anos.", "location": "São Paulo, SP", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor R / Shiny", "company": "Analytics Lab", "description": "Análise estatística com R, dashboards com Shiny e visualização com ggplot2. Integração com APIs. 2+ anos.", "location": "Belo Horizonte, MG", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Product Manager Técnico", "company": "Product Team", "description": "Gestão de produto técnico com backlog, roadmaps e métricas. Trabalho próximo com engenharia e design. 4+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Solidity / Web3", "company": "Blockchain Inc", "description": "Smart contracts com Solidity, Hardhat e Chainlink. Integração com React e wallets. 2+ anos de experiência.", "location": "Remoto", "modality": "Remoto Internacional", "source": "GitHub Jobs"},
        {"title": "Desenvolvedor .NET / Angular", "company": "Enterprise Solutions", "description": "Aplicações enterprise com .NET 7, Angular 16 e SQL Server. Padrões de arquitetura e testes unitários.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Rust / WebAssembly", "company": "Wasm Tech", "description": "Desenvolvimento de módulos WebAssembly com Rust. Integração com React e otimização de performance.", "location": "São Paulo, SP", "modality": "Remoto", "source": "Glassdoor"},
        {"title": "Engenheiro de Trust & Safety", "company": "Social Platform", "description": "Desenvolvimento de ferramentas de moderação e análise de conteúdo. Python, Elasticsearch e ML. 3+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Kotlin Multiplatform", "company": "Mobile Platform", "description": "Apps com Kotlin Multiplatform e Jetpack Compose. Shared business logic e native UI. 2+ anos.", "location": "Porto Alegre, RS", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Data Platform Engineer", "company": "DataOps", "description": "PLATAforma de dados com Apache Kafka, Flink e Spark Streaming. Pipelines em tempo real. 4+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Desenvolvedor Haskell / Functional", "company": "Functional Labs", "description": "Sistemas funcionais com Haskell e PureScript. Type system avançado e testes com QuickCheck. 3+ anos.", "location": "São Paulo, SP", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Cloud Architect", "company": "Cloud Consulting", "description": "Arquitetura cloud com AWS, Azure e GCP. Design de soluções multi-cloud e migration strategies. 8+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Desenvolvedor Backend Python Django", "company": "CMS Solutions", "description": "Desenvolvimento com Django, Django REST Framework e PostgreSQL. Celery para tasks assíncronas. 3+ anos.", "location": "Belo Horizonte, MG", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "SRE / Platform Engineer", "company": "Infra Ops", "description": "Site reliability com Go, Terraform, Ansible e observabilidade. SLIs, SLOs e error budgets. 4+ anos.", "location": "São Paulo, SP", "modality": "Remoto", "source": "InfoJobs"},
        {"title": "Desenvolvedor Java / Quarkus", "company": "Cloud Java", "description": "Microserviços com Java e Quarkus. GraalVM Native Image e Kubernetes. 3+ anos de experiência.", "location": "Florianópolis, SC", "modality": "Híbrido", "source": "GitHub Jobs"},
        {"title": "AI Engineer / LLM Applications", "company": "AI Products", "description": "Aplicações com LLMs, LangChain e向量数据库. RAG systems e fine-tuning. Python e cloud. 3+ anos.", "location": "São Paulo, SP", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Desenvolvedor Scala / Akka", "company": "Distributed Systems", "description": "Sistemas distribuídos com Scala, Akka e Apache Kafka. Reactive programming e CQRS. 4+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Technical Recruiter / Tech Sourcer", "company": "HR Tech", "description": "Recrutamento técnico com sourcing em GitHub, LinkedIn e Stack Overflow. 2+ anos de experiência.", "location": "São Paulo, SP", "modality": "Remoto", "source": "Catho"},
        {"title": "Desenvolvedor .NET MAUI", "company": "Mobile Solutions", "description": "Apps multiplataforma com .NET MAUI e C#. Integração com APIs REST e Firebase. 2+ anos.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Database Administrator / DBA", "company": "Data Infra", "description": "Administração de bancos PostgreSQL e MySQL. Backup, restore, performance tuning e replicação. 5+ anos.", "location": "São Paulo, SP", "modality": "Presencial", "source": "InfoJobs"},
        {"title": "Desenvolvedor Python / Django REST", "company": "API Factory", "description": "APIs REST com Django REST Framework e DRF. Autenticação JWT, paginação e versionamento. 3+ anos.", "location": "Remoto", "modality": "Remoto Nacional", "source": "LinkedIn"},
        {"title": "Software Engineer Intern", "company": "Tech Academy", "description": "Estágio em engenharia de software com Python e JavaScript. Projeto de TCC e mentoria técnica.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Catho"},
        {"title": "Desenvolvedor Frontend Angular", "company": "Enterprise Frontend", "description": "Aplicações enterprise com Angular 17, RxJS e NgRx. TypeScript e testes com Jasmine/Karma.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Blockchain Developer", "company": "Crypto Tech", "description": "Smart contracts com Solidity e Web3.js. Integração com DeFi protocols e NFTs. 2+ anos.", "location": "Remoto", "modality": "Remoto Internacional", "source": "GitHub Jobs"},
        {"title": "Desenvolvedor Python / Flask", "company": "Micro API", "description": "APIs leves com Flask e Flask-RESTful. SQLAlchemy, Marshmallow e testes com pytest. 2+ anos.", "location": "Florianópolis, SC", "modality": "Remoto", "source": "InfoJobs"},
        {"title": "IT Security Consultant", "company": "Secure Solutions", "description": "Consultoria em segurança da informação. Análise de riscos, compliance LGPD e pentest. 5+ anos.", "location": "São Paulo, SP", "modality": "Presencial", "source": "Glassdoor"},
        {"title": "Desenvolvedor Go / Terraform", "company": "Infrastructure as Code", "description": "Infraestrutura com Terraform e Go. Provisionamento de cloud resources e automação de deploy.", "location": "São Paulo, SP", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Desenvolvedor Fullstack TypeScript", "company": "TS Solutions", "description": "Fullstack com TypeScript, Node.js, React e PostgreSQL. Monorepo com Turborepo e NX.", "location": "Curitiba, PR", "modality": "Híbrido", "source": "GitHub Jobs"},
        {"title": "ML Engineer / Computer Vision", "company": "Vision AI", "description": "Modelos de visão computacional com PyTorch, OpenCV e TensorRT. Deploy em edge devices. 4+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Desenvolvedor PHP / CodeIgniter", "company": "Legacy Systems", "description": "Manutenção e evolução de sistemas com PHP 8 e CodeIgniter 4. MySQL e APIs REST. 3+ anos.", "location": "Rio de Janeiro, RJ", "modality": "Híbrido", "source": "Catho"},
        {"title": "Platform Engineer / PaaS", "company": "Platform Team", "description": "Construção de plataformas internas com Backstage, Kubernetes e Istio. Developer experience e self-service.", "location": "São Paulo, SP", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Desenvolvedor C++ / Qt", "company": "Desktop Apps", "description": "Aplicações desktop com C++ e Qt Framework. UI customizada e performance gráfica. 3+ anos.", "location": "São Paulo, SP", "modality": "Presencial", "source": "InfoJobs"},
        {"title": "Data Scientist / ML Ops", "company": "ML Platform", "description": "Deploy e monitoramento de modelos ML com MLflow, Kubeflow e Python. Feature stores e experiment tracking.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
        {"title": "Desenvolvedor NestJS / GraphQL", "company": "API Design", "description": "APIs GraphQL com NestJS e Apollo Server. TypeGraphQL, resolvers e subscriptions. 2+ anos.", "location": "Florianópolis, SC", "modality": "Remoto", "source": "LinkedIn"},
        {"title": "Cloud Solutions Architect", "company": "Cloud Partners", "description": "Design de soluções cloud com AWS Well-Architected Framework. Migration e modernização de aplicações.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Indeed"},
        {"title": "Desenvolvedor Elixir / Phoenix", "company": "Realtime Systems", "description": "Sistemas em tempo real com Elixir, Phoenix e LiveView. WebSockets e presença. 3+ anos.", "location": "São Paulo, SP", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Tech Lead / Engineering Manager", "company": "Engineering Leadership", "description": "Liderança técnica e gestão de equipes de engenharia. 10+ anos de experiência em desenvolvimento.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Backend Django / DRF", "company": "Web Services", "description": "APIs e plataformas web com Django, DRF e Celery. Redis para caching e filas. 3+ anos de experiência.", "location": "Belo Horizonte, MG", "modality": "Híbrido", "source": "InfoJobs"},
        {"title": "Firmware Engineer", "company": "Hardware Solutions", "description": "Desenvolvimento de firmware em C para microcontroladores STM32 e ESP32. IoT e protocolos de comunicação.", "location": "Campinas, SP", "modality": "Presencial", "source": "Catho"},
        {"title": "Desenvolvedor React Native / Expo", "company": "Mobile Apps Co", "description": "Apps mobile com React Native e Expo. TypeScript, Navigation e integração com APIs nativas.", "location": "São Paulo, SP", "modality": "Remoto", "source": "GitHub Jobs"},
        {"title": "Senior DevOps Engineer", "company": "Infra Platform", "description": "CI/CD com GitHub Actions, ArgoCD e GitLab CI. Infra como código com Terraform e Pulumi. 6+ anos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "LinkedIn"},
        {"title": "Desenvolvedor Python / Streamlit", "company": "Data Apps", "description": "Aplicações data com Python, Streamlit e Plotly Dash. Dashboards interativos e visualizações.", "location": "Remoto", "modality": "Remoto Nacional", "source": "InfoJobs"},
        {"title": "Principal Engineer", "company": "Tech Leadership", "description": "Liderança técnica em nível principal. Arquitetura, mentoring e definição de padrões técnicos.", "location": "São Paulo, SP", "modality": "Híbrido", "source": "Glassdoor"},
    ]
    return base_jobs

def generate_mock_jobs_if_empty(db_file: Path, job_title: str = "Desenvolvedor Backend"):
    """Gera vagas mock realistas para amostragem se a base estiver vazia."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM market_raw_jobs")
    count = cursor.fetchone()[0]

    if count == 0:
        import uuid
        from datetime import datetime, timedelta

        sample_jobs = _generate_sample_jobs(job_title)

        now = datetime.now()
        for i, j in enumerate(sample_jobs):
            job_id = str(uuid.uuid4())
            pub_date = now - timedelta(days=i * 3 + 1)
            cursor.execute('''
                INSERT INTO market_raw_jobs (id, title, company, description, location, modality, source, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, j["title"], j["company"], j["description"], j["location"], j["modality"], j["source"], pub_date.isoformat()))
        
        conn.commit()
    conn.close()

def extract_job_with_ai(client: OpenAI, selected_model: str, job_text: str, target_stack: List[str]) -> Dict[str, Any]:
    """Usa IA para extrair dados estruturados de uma vaga de forma rigorosa."""
    prompt = f"""
Você é um extrator de dados de vagas de emprego.
Dada a descrição de vaga abaixo, extraia os campos em formato JSON estrito:

REGRAS:
1. Grounding: Apenas extraia o que estiver EXPLICITAMENTE mencionado na vaga. Nunca invente dados.
2. Se um campo não estiver mencionado, retorne null / array vazio.
3. Normalização: Mantenha nomes de tecnologias limpos.

JSON Esperado:
{{
  "is_relevant": true|false,
  "role_level": "Júnior"|"Pleno"|"Sênior"|"Especialista"|null,
  "exp_years_min": número|null,
  "exp_years_max": número|null,
  "req_techs": ["tecnologia1", "tecnologia2"],
  "desirable_techs": ["tecnologia1"],
  "certifications": ["certificação1"],
  "soft_skills": ["comunicação", "trabalho em equipe"],
  "salary_min": número|null,
  "salary_max": número|null,
  "currency": "BRL"|"USD"|null
}}

Stack Alvo de Referência: {", ".join(target_stack)}

Descrição da Vaga:
{job_text}
"""
    try:
        response = client.chat.completions.create(
            model=selected_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content or "{}"
        
        # Strip thinking tag se houver
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        data = json.loads(content)
        return data
    except Exception as e:
        # Fallback via regex/heuristic para não falhar a análise
        return {
            "is_relevant": True,
            "role_level": None,
            "exp_years_min": None,
            "exp_years_max": None,
            "req_techs": [],
            "desirable_techs": [],
            "certifications": [],
            "soft_skills": [],
            "salary_min": None,
            "salary_max": None,
            "currency": None
        }

def run_market_analysis(
    db_file: Path,
    client: OpenAI,
    selected_model: str,
    job_title: str,
    target_stack: str,
    seniority: str,
    location: str,
    time_window: str,
    negative_keywords: str = ""
) -> Dict[str, Any]:
    """Executa o pipeline completo de Inteligência de Mercado."""

    # 1. Garante vagas de amostragem no DB
    init_market_db(db_file)
    generate_mock_jobs_if_empty(db_file, job_title)

    stack_list = [s.strip() for s in target_stack.split(",") if s.strip()]
    neg_list = [k.strip().lower() for k in negative_keywords.split(",") if k.strip()]

    # 2. Busca vagas brutas
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, description, location, modality, source, published_at FROM market_raw_jobs")
    raw_jobs = cursor.fetchall()

    extracted_jobs = []
    tech_counts_req: Dict[str, int] = {}
    tech_counts_desirable: Dict[str, int] = {}
    soft_skills_counts: Dict[str, int] = {}
    cert_counts: Dict[str, int] = {}
    modality_counts: Dict[str, int] = {}
    exp_years_list: List[int] = []
    salaries_list: List[float] = []

    total_jobs = len(raw_jobs)
    relevant_count = 0

    for j in raw_jobs:
        job_id, title, company, description, loc, mod, source, pub_at = j
        job_text = f"Título: {title}\nEmpresa: {company}\nLocalização: {loc}\nModalidade: {mod}\nDescrição:\n{description}"

        # Negative keyword filter
        job_text_lower = (title + " " + description).lower()
        if neg_list and any(nk in job_text_lower for nk in neg_list):
            continue

        # Extração via IA
        extracted = extract_job_with_ai(client, selected_model, job_text, stack_list)
        
        # Normalização de tecnologias exigidas
        req_techs_norm = [normalize_tech(t) for t in extracted.get("req_techs", [])]
        des_techs_norm = [normalize_tech(t) for t in extracted.get("desirable_techs", [])]
        
        # Filtro de relevância básico
        is_rel = extracted.get("is_relevant", True)
        if is_rel:
            relevant_count += 1
            
            # Modalidade
            mod_label = mod or "Não informado"
            modality_counts[mod_label] = modality_counts.get(mod_label, 0) + 1

            # Anos de experiência
            exp_min = extracted.get("exp_years_min")
            if exp_min is not None and isinstance(exp_min, (int, float)):
                exp_years_list.append(int(exp_min))

            # Salários
            sal_min = extracted.get("salary_min")
            if sal_min is not None and isinstance(sal_min, (int, float)):
                salaries_list.append(float(sal_min))

            # Tecnologias Obrigatórias
            for t in req_techs_norm:
                tech_counts_req[t] = tech_counts_req.get(t, 0) + 1

            # Tecnologias Desejáveis
            for t in des_techs_norm:
                tech_counts_desirable[t] = tech_counts_desirable.get(t, 0) + 1

            # Soft Skills
            for ss in extracted.get("soft_skills", []):
                ss_norm = ss.strip().capitalize()
                soft_skills_counts[ss_norm] = soft_skills_counts.get(ss_norm, 0) + 1

            # Certificações
            for c in extracted.get("certifications", []):
                c_norm = c.strip()
                cert_counts[c_norm] = cert_counts.get(c_norm, 0) + 1

        extracted_jobs.append({
            "id": job_id,
            "title": title,
            "company": company,
            "location": loc,
            "modality": mod,
            "source": source,
            "is_relevant": is_rel,
            "req_techs": req_techs_norm,
            "desirable_techs": des_techs_norm,
            "role_level": extracted.get("role_level"),
            "exp_years_min": extracted.get("exp_years_min"),
            "exp_years_max": extracted.get("exp_years_max"),
            "soft_skills": extracted.get("soft_skills", []),
            "certifications": extracted.get("certifications", []),
            "salary_min": extracted.get("salary_min"),
            "salary_max": extracted.get("salary_max"),
            "currency": extracted.get("currency"),
            "raw_description": description
        })

    # Estatísticas e Medianas
    rel_total = max(relevant_count, 1)

    # Ranking Techs Obrigatórias
    req_ranking = [
        {"name": tech, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for tech, count in sorted(tech_counts_req.items(), key=lambda x: x[1], reverse=True)
    ]

    # Ranking Techs Desejáveis
    desirable_ranking = [
        {"name": tech, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for tech, count in sorted(tech_counts_desirable.items(), key=lambda x: x[1], reverse=True)
    ]

    # Modalidade Ranking
    modality_ranking = [
        {"name": mod, "count": count, "percentage": round((count / rel_total) * 100, 1)}
        for mod, count in sorted(modality_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # Anos de experiência (Mediana + Distribuição)
    exp_years_sorted = sorted(exp_years_list)
    if exp_years_sorted:
        mid = len(exp_years_sorted) // 2
        exp_median = exp_years_sorted[mid]
    else:
        exp_median = 3

    # Score de Confiança
    if rel_total >= 10:
        confidence = "Alta"
        confidence_reason = f"Amostra sólida com {rel_total} vagas relevantes de múltiplas fontes."
    elif rel_total >= 5:
        confidence = "Média"
        confidence_reason = f"Amostra moderada de {rel_total} vagas. Recomendado expandir a busca."
    else:
        confidence = "Baixa"
        confidence_reason = f"Amostra reduzida ({rel_total} vagas). Use os dados com cautela."

    report_result = {
        "summary": {
            "job_title": job_title,
            "target_stack": stack_list,
            "seniority": seniority,
            "location": location,
            "time_window": time_window,
            "total_jobs_scanned": total_jobs,
            "relevant_jobs_analyzed": relevant_count,
            "discarded_jobs": total_jobs - relevant_count,
            "confidence_score": confidence,
            "confidence_reason": confidence_reason,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "statistics": {
            "required_technologies": req_ranking[:10],
            "desirable_technologies": desirable_ranking[:8],
            "exp_years_median": exp_median,
            "exp_years_distribution": {
                "0-1 ano": len([e for e in exp_years_list if e <= 1]),
                "2-3 anos": len([e for e in exp_years_list if 2 <= e <= 3]),
                "4-5 anos": len([e for e in exp_years_list if 4 <= e <= 5]),
                "5+ anos": len([e for e in exp_years_list if e > 5])
            },
            "modalities": modality_ranking,
            "top_soft_skills": [
                {"name": k, "count": v} for k, v in sorted(soft_skills_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            ],
            "top_certifications": [
                {"name": k, "count": v} for k, v in sorted(cert_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
        },
        "sample_jobs": extracted_jobs[:30]
    }

    # Persiste o relatório gerado
    import uuid
    report_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO market_reports (id, job_title, target_stack, seniority, location, time_window, total_jobs, relevant_jobs, confidence_score, report_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        report_id, job_title, target_stack, seniority, location, time_window,
        total_jobs, relevant_count, confidence, json.dumps(report_result)
    ))
    conn.commit()
    conn.close()

    return report_result
