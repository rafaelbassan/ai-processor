# 🚀 VectoSports AI Results Server

Servidor FastAPI para gerenciar uploads e processamento de análises biomecânicas do VectoSports. Implementa os 4 endpoints definidos no protocolo ProbPose Worker.

---

## 📋 Visão Geral

Este servidor implementa os endpoints necessários para:

1. **Gerar URLs de upload** - Disponibiliza URLs presigned para o worker fazer upload de arquivos
2. **Receber uploads** - Aceita uploads binários de vídeos, JSON e outros arquivos
3. **Processar resultados** - Recebe metadata e inicia processamento das análises
4. **Consultar status** - Retorna status e progresso do processamento

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────┐
│  ProbPose Worker                             │
│  (em outro container/serviço)                │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
  POST       PUT        POST      GET
  (1)        (2)        (3)       (4)
    │          │          │          │
    └──────────┴──────────┴──────────┴─────────┐
                                                │
                    ┌───────────────────────────┘
                    │
                    ▼
        ┌─────────────────────────┐
        │ VectoSports AI Server   │
        │ (FastAPI - Docker)      │
        │                         │
        │ ✓ Upload Manager        │
        │ ✓ Job Processor         │
        │ ✓ Status Tracker        │
        │ ✓ File Storage          │
        └─────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
   /data/uploads          Database/Memory
   (arquivos)             (jobs, sessions)
```

---

## 🔌 Endpoints

### 1️⃣ POST /api/results/get-upload-urls

Gera URLs presigned para upload de arquivos.

**Request:**
```json
{
  "jobId": "abc123",
  "files": ["result_video.mp4", "keypoints.json", "report.pdf"]
}
```

**Response:**
```json
{
  "urls": {
    "result_video.mp4": "http://localhost:8000/api/upload/abc123/token1",
    "keypoints.json": "http://localhost:8000/api/upload/abc123/token2",
    "report.pdf": "http://localhost:8000/api/upload/abc123/token3"
  }
}
```

**Características:**
- ✅ Gera token único para cada arquivo
- ✅ Tokens expiram em 3 horas
- ✅ Limite de tamanho: 1GB por arquivo
- ✅ Suporta múltiplos uploads paralelos

---

### 2️⃣ PUT /api/upload/{job_id}/{token}

Recebe upload de arquivo binário.

**Request:**
```http
PUT /api/upload/abc123/token1 HTTP/1.1
Content-Type: application/octet-stream
Content-Length: 5242880

[arquivo binário]
```

**Response:**
```json
{
  "status": "uploaded",
  "filename": "result_video.mp4",
  "size": 5242880,
  "uploaded_at": "2026-01-21T10:30:15"
}
```

**Características:**
- ✅ Valida token e expiração
- ✅ Salva arquivo em `/data/uploads/{job_id}/`
- ✅ Suporta uploads acima de 1GB
- ✅ Retorna informações do arquivo uploadado

---

### 3️⃣ POST /api/results

Recebe metadata e inicia processamento.

**Request:**
```json
{
  "jobId": "abc123",
  "analysisId": "abc123",
  "timestamp": "2026-01-21T10:30:15",
  "analysisConfig": {
    "sport": "swimming",
    "analysisType": "biomechanical",
    "focusAreas": ["shoulder", "knee", "hip"]
  },
  "athleteData": {
    "name": "João Silva",
    "age": 28,
    "height": 1.80,
    "weight": 75,
    "sport": "natação"
  },
  "videoInfo": {
    "filename": "test_video.mp4",
    "size": 104857600,
    "duration": 120
  },
  "metadata": {
    "timestamp": "2026-01-21T10:30:00",
    "source": "camera_1",
    "location": "pool_1"
  },
  "uploadResultsUrl": "http://seu-servico.com/upload",
  "probposeOutput": {
    "statistics": {
      "total_frames": 300,
      "keypoints_per_frame": 17,
      "average_confidence": 0.92
    },
    "outputFiles": {
      "result_video.mp4": "http://localhost:8000/api/upload/abc123/token1",
      "keypoints.json": "http://localhost:8000/api/upload/abc123/token2",
      "report.pdf": "http://localhost:8000/api/upload/abc123/token3"
    },
    "clipsInfo": []
  },
  "originalPayload": {}
}
```

**Response:**
```json
{
  "token": "proc_xyz789",
  "message": "Job received, files stored, processing started",
  "files_ready": ["result_video.mp4", "keypoints.json", "report.pdf"]
}
```

**Características:**
- ✅ Valida que todos os arquivos foram uploadados
- ✅ Inicia processamento assíncrono
- ✅ Retorna token único para polling
- ✅ Preserva todos os dados contextuais

---

### 4️⃣ GET /api/results/status/{token}

Retorna status do processamento.

**Request:**
```http
GET /api/results/status/proc_xyz789 HTTP/1.1
```

**Response (Processando):**
```json
{
  "token": "proc_xyz789",
  "status": "processing",
  "progress": 45,
  "result": null,
  "error": null
}
```

**Response (Completo):**
```json
{
  "token": "proc_xyz789",
  "status": "completed",
  "progress": 100,
  "result": {
    "athlete": {...},
    "analysis_config": {...},
    "processed_at": "2026-01-21T10:31:00",
    "summary": "Análise biomecânica completada..."
  },
  "error": null
}
```

**Response (Falha):**
```json
{
  "token": "proc_xyz789",
  "status": "failed",
  "progress": 0,
  "result": null,
  "error": "Descrição do erro"
}
```

**Características:**
- ✅ Status: `processing`, `completed`, `failed`
- ✅ Progresso de 0-100%
- ✅ Timeout: 5 minutos (recomendado para polling do worker)
- ✅ Resultado completo quando completado

---

## 📊 Health Check

**Request:**
```http
GET /health HTTP/1.1
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-21T10:30:15",
  "active_jobs": 5,
  "active_sessions": 3
}
```

---

## 🐳 Docker Setup

### 1. Clonar/Preparar o Projeto

```bash
cd vectosports_ai
```

### 2. Configurar Variáveis de Ambiente

```bash
# Copiar template
cp .env.example .env

# Editar conforme necessário
nano .env
```

### 3. Build da Imagem

```bash
docker-compose build
```

### 4. Deploy

```bash
# Iniciar serviço
docker-compose up -d

# Verificar logs
docker-compose logs -f vectosports-ai-server

# Parar serviço
docker-compose down
```

### 5. Testar

```bash
# Health check
curl http://localhost:8000/health

# Debug: listar sessões
curl http://localhost:8000/debug/sessions

# Debug: listar jobs
curl http://localhost:8000/debug/jobs
```

---

## 📁 Estrutura de Diretórios

```
vectosports_ai/
├── api/
│   ├── server.py              # Servidor FastAPI (este arquivo)
│   ├── requirements.txt        # Dependências Python
│   └── __init__.py
├── ai_agents/
│   └── vectosports/           # Agentes de IA
├── Dockerfile                 # Build da imagem
├── docker-compose.yml         # Orquestração
├── .env.example               # Template de variáveis
└── data/
    └── uploads/               # Diretório de uploads (criado automaticamente)
```

### Armazenamento

**Local (desenvolvimento):**
```
./data/uploads/
├── job_1/
│   ├── result_video.mp4
│   ├── keypoints.json
│   └── report.pdf
├── job_2/
│   └── ...
```

**Docker:**
```
/data/uploads/
├── job_1/
│   └── ...
```

---

## 🔄 Fluxo Completo de Processamento

### Timeline de um Job

```
T=0s    Worker: POST /api/results/get-upload-urls
        Server: gera 3 tokens e URLs
        Worker: recebe URLs

T=1s    Worker: PUT arquivo 1 (100MB)
        Worker: PUT arquivo 2 (10MB)
        Worker: PUT arquivo 3 (20MB)
        (uploads em paralelo)

T=30s   Worker: POST /api/results com metadata
        Server: valida arquivos, inicia processamento
        Worker: recebe token "proc_xyz"

T=32s   Worker: GET /api/results/status/proc_xyz
        Server: "processing", progress: 10%

T=35s   Worker: GET /api/results/status/proc_xyz
        Server: "processing", progress: 50%

T=40s   Worker: GET /api/results/status/proc_xyz
        Server: "completed", progress: 100%, result: {...}

T=41s   Worker: ACK no RabbitMQ
T=42s   Worker: próximo job
```

---

## 🛠️ Integração com ProbPose Worker

### Variáveis de Ambiente do Worker

```bash
# Apontar para este servidor
RESULTS_SERVER_URL=http://vectosports-ai-server:8000
RESULTS_ENDPOINT=/api/results
GET_UPLOAD_URLS_ENDPOINT=/api/results/get-upload-urls
STATUS_ENDPOINT=/api/results/status
```

### Docker Compose Completo (com Worker)

```yaml
version: '3.8'

services:
  vectosports-ai-server:
    # ... (como definido em docker-compose.yml)
    networks:
      - vectosports-network

  probpose-worker:
    build:
      context: ../probpose
      dockerfile: Dockerfile
    environment:
      RESULTS_SERVER_URL: http://vectosports-ai-server:8000
      RABBITMQ_HOST: rabbitmq
      # ... outras variáveis
    networks:
      - vectosports-network
    depends_on:
      - vectosports-ai-server

networks:
  vectosports-network:
    driver: bridge
```

---

## 📝 Endpoints de Debug (Development Only)

### 1. GET /debug/sessions

Lista todas as sessões de upload ativas.

```bash
curl http://localhost:8000/debug/sessions
```

**Response:**
```json
{
  "total": 2,
  "sessions": [
    {
      "session_id": "abc123_token1",
      "job_id": "abc123",
      "filename": "result_video.mp4",
      "uploaded": false,
      "expires_in": "02:45:30"
    },
    {
      "session_id": "abc123_token2",
      "job_id": "abc123",
      "filename": "keypoints.json",
      "uploaded": true,
      "expires_in": "02:44:15"
    }
  ]
}
```

### 2. GET /debug/jobs

Lista todos os jobs.

```bash
curl http://localhost:8000/debug/jobs
```

**Response:**
```json
{
  "total": 3,
  "jobs": [
    {
      "token": "proc_xyz1",
      "job_id": "abc123",
      "status": "processing",
      "progress": 45,
      "athlete": "João Silva",
      "created_at": "2026-01-21T10:30:00"
    },
    {
      "token": "proc_xyz2",
      "job_id": "abc124",
      "status": "completed",
      "progress": 100,
      "athlete": "Maria Santos",
      "created_at": "2026-01-21T10:25:00"
    }
  ]
}
```

### 3. DELETE /debug/jobs/{token}

Remove um job (para testes).

```bash
curl -X DELETE http://localhost:8000/debug/jobs/proc_xyz1
```

---

## 🔐 Segurança

### Em Desenvolvimento
- ✅ CORS aberto (`*`)
- ✅ Endpoints de debug disponíveis
- ✅ Sem autenticação

### Em Produção
- ❌ Alterar `CORS_ORIGINS` para domínios específicos
- ❌ Remover endpoints `/debug/*`
- ⚠️ Implementar autenticação (JWT, OAuth2, etc.)
- ⚠️ Usar HTTPS
- ⚠️ Implementar rate limiting
- ⚠️ Validar tamanho de uploads

---

## 🧪 Testes

### 1. Teste de Saúde

```bash
curl http://localhost:8000/health
```

### 2. Teste Completo

```bash
# 1. Obter URLs
curl -X POST http://localhost:8000/api/results/get-upload-urls \
  -H "Content-Type: application/json" \
  -d '{
    "jobId": "test_123",
    "files": ["video.mp4", "data.json"]
  }'

# Resposta:
# {
#   "urls": {
#     "video.mp4": "http://localhost:8000/api/upload/test_123/token1",
#     "data.json": "http://localhost:8000/api/upload/test_123/token2"
#   }
# }

# 2. Upload arquivo (exemplo)
curl -X PUT http://localhost:8000/api/upload/test_123/token1 \
  --data-binary @video.mp4

# 3. Enviar metadata e iniciar processamento
curl -X POST http://localhost:8000/api/results \
  -H "Content-Type: application/json" \
  -d '{
    "jobId": "test_123",
    "analysisId": "test_123",
    "timestamp": "2026-01-21T10:30:15",
    "analysisConfig": {
      "sport": "swimming",
      "focusAreas": ["shoulder"]
    },
    "athleteData": {
      "name": "Test Athlete",
      "sport": "swimming"
    },
    "videoInfo": {
      "filename": "video.mp4",
      "size": 1000000,
      "duration": 60
    },
    "metadata": {
      "timestamp": "2026-01-21T10:30:00"
    },
    "probposeOutput": {
      "outputFiles": {
        "video.mp4": "http://localhost:8000/api/upload/test_123/token1",
        "data.json": "http://localhost:8000/api/upload/test_123/token2"
      }
    }
  }'

# Resposta:
# {
#   "token": "proc_xyz...",
#   "message": "Job received, files stored, processing started",
#   "files_ready": ["video.mp4", "data.json"]
# }

# 4. Verificar status
curl http://localhost:8000/api/results/status/proc_xyz...
```

---

## 📦 Dependências

Ver [requirements.txt](requirements.txt):

- **fastapi** - Framework Web
- **uvicorn** - ASGI server
- **pydantic** - Validação de dados
- **python-dotenv** - Gerenciamento de variáveis de ambiente
- **python-multipart** - Suporte a uploads multipart
- **google-adk** - SDK do Google AI (para agentes)

---

## 🚀 Próximos Passos

1. **Adaptar para produção:**
   - [ ] Configurar HTTPS
   - [ ] Implementar autenticação
   - [ ] Usar banco de dados real (PostgreSQL, MongoDB)
   - [ ] Configurar load balancing
   - [ ] Implementar rate limiting

2. **Expandir funcionalidades:**
   - [ ] Webhooks para notificações
   - [ ] Queue para processamento assíncrono (Celery, RQ)
   - [ ] Download de resultados
   - [ ] Histórico de jobs
   - [ ] Analytics e dashboards

3. **Integrar com agentes:**
   - [ ] Conectar ao root_agent para análises reais
   - [ ] Customizar processamento por esporte
   - [ ] Armazenar resultados em BD

---

## 📞 Suporte

### Logs

```bash
# Ver logs em tempo real
docker-compose logs -f vectosports-ai-server

# Ver últimas 100 linhas
docker-compose logs --tail=100 vectosports-ai-server
```

### Troubleshooting

| Problema | Solução |
|----------|---------|
| Porta 8000 em uso | Alterar `SERVER_PORT` em `.env` ou mudar porta do host |
| Erro de permissão em `/data/uploads` | Verificar permissões: `chmod 755 data/` |
| Container não inicia | Ver logs: `docker-compose logs vectosports-ai-server` |
| Conexão recusada pelo worker | Verificar URL em `RESULTS_SERVER_URL` |

---

## 📄 Licença

Projeto proprietário VectoSports
