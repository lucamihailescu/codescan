# MLP Code Guardian

A Data Loss Prevention (DLP) solution that scans directories for sensitive data patterns and identifies duplicate or similar files across source and target locations.

## Features

- **File Indexing**: Scan and index files with content extraction for various document types
- **Similarity Detection**: TF-IDF vectorization with configurable thresholds to find duplicate or similar files
- **Multi-format Support**: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), and text files
- **Authentication**: Microsoft Entra ID (Azure AD) integration with role-based access
- **Flexible Storage**: SQLite (default) or Redis backends with connection pooling
- **Real-time Progress**: WebSocket-based indexing and scanning progress updates
- **Parallel Processing**: Multi-threaded indexing and scanning for improved performance
- **Configurable Patterns**: Globally ignored file patterns for exclusions
- **User Activity Logging**: Detailed logging with user context for audit trails
- **Sensitivity Presets**: Low, medium, high, and custom similarity thresholds

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│    Backend      │────▶│    Storage      │
│  React + Vite   │     │    FastAPI      │     │ SQLite / Redis  │
│     (Nginx)     │     │   (Uvicorn)     │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────────┐
        └──────────────▶│  Microsoft      │
                        │  Entra ID       │
                        └─────────────────┘
```

## Quick Start

### Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Environment Variables

Create `.env` files based on the examples:

**Backend** (`backend/.env`):
```env
# Database
DATABASE_URL=sqlite:///./dlp.db

# Storage backend (sqlite or redis)
STORAGE_BACKEND=sqlite

# Connection pooling
DB_POOL_SIZE=10
DB_POOL_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
DB_POOL_PRE_PING=true

# Parallel processing
THREADING_ENABLED=false
THREADING_MAX_WORKERS=4
THREADING_BATCH_SIZE=50

# Similarity matching
SIMILARITY_SENSITIVITY=medium
SIMILARITY_THRESHOLD=0.65
SIMILARITY_HIGH_CONFIDENCE_THRESHOLD=0.85
SIMILARITY_EXACT_MATCH_THRESHOLD=0.98

# Vectorization
VECTORIZATION_N_FEATURES=8192
VECTORIZATION_NGRAM_MIN=1
VECTORIZATION_NGRAM_MAX=3

# Microsoft Entra ID (optional)
ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_REQUIRED_ROLE=admin

# Redis (if using redis storage)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_POOL_MAX_CONNECTIONS=50
```

**Frontend** (`frontend/.env`):
```env
VITE_API_URL=http://localhost:8000
VITE_ENTRA_CLIENT_ID=your-client-id
VITE_ENTRA_TENANT_ID=your-tenant-id
VITE_ENTRA_REDIRECT_URI=http://localhost:5173
VITE_ENTRA_POST_LOGOUT_URI=http://localhost:5173
```

> **Note:** Both backend and frontend include `.env.example` files with comprehensive documentation for all available configuration options.

---

## Docker Deployment

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+

### Development Deployment

```bash
# Build and run with SQLite storage
docker-compose up -d

# Build and run with Redis storage
docker-compose --profile redis up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production Deployment

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Run with environment file
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Docker Images

| Image | Description | Port |
|-------|-------------|------|
| `mlp-code-guardian-backend` | FastAPI backend | 8000 |
| `mlp-code-guardian-frontend` | React + Nginx | 80 |
| `redis:7-alpine` | Redis cache (optional) | 6379 |

### Docker Environment Variables

Create a `.env` file at the project root:

```env
# Registry (for production)
REGISTRY=ghcr.io
IMAGE_PREFIX=myorg
TAG=latest

# Backend
DATABASE_URL=sqlite:///./data/dlp_sentinel.db
STORAGE_BACKEND=sqlite
REDIS_URL=redis://redis:6379

# Authentication
ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_REQUIRED_ROLE=admin

# Frontend (build-time)
VITE_API_URL=https://api.yourdomain.com
VITE_ENTRA_CLIENT_ID=your-client-id
VITE_ENTRA_TENANT_ID=your-tenant-id
VITE_ENTRA_REDIRECT_URI=https://yourdomain.com

# Volume mounts for scanning
SCAN_SOURCE_DIR=/path/to/source/files
SCAN_TARGET_DIR=/path/to/target/files
```

### Mounting Directories for Scanning

To scan files on your host system, mount them as volumes:

```yaml
# In docker-compose.yml
volumes:
  - /host/path/to/source:/mnt/source:ro
  - /host/path/to/target:/mnt/target:ro
```

Then configure scans to use `/mnt/source` and `/mnt/target` as paths.

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes 1.24+
- kubectl configured
- Container registry access (e.g., Docker Hub, ACR, ECR, GCR)

### Converting Docker Compose to Kubernetes

Use [Kompose](https://kompose.io/) to convert:

```bash
# Install kompose
brew install kompose  # macOS
# or
curl -L https://github.com/kubernetes/kompose/releases/download/v1.31.2/kompose-linux-amd64 -o kompose

# Convert to Kubernetes manifests
kompose convert -f docker-compose.prod.yml -o k8s/
```

### Manual Kubernetes Manifests

Create the following files in a `k8s/` directory:

**Namespace** (`k8s/namespace.yaml`):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mlp-code-guardian
```

**Backend Deployment** (`k8s/backend-deployment.yaml`):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: mlp-code-guardian
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: ghcr.io/myorg/mlp-code-guardian-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: STORAGE_BACKEND
          value: "redis"
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: mlp-secrets
              key: redis-url
        - name: ENTRA_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: mlp-secrets
              key: entra-tenant-id
        - name: ENTRA_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: mlp-secrets
              key: entra-client-id
        resources:
          limits:
            cpu: "1"
            memory: "1Gi"
          requests:
            cpu: "500m"
            memory: "512Mi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: backend-data
```

**Frontend Deployment** (`k8s/frontend-deployment.yaml`):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: mlp-code-guardian
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
      - name: frontend
        image: ghcr.io/myorg/mlp-code-guardian-frontend:latest
        ports:
        - containerPort: 80
        resources:
          limits:
            cpu: "500m"
            memory: "256Mi"
          requests:
            cpu: "250m"
            memory: "128Mi"
        livenessProbe:
          httpGet:
            path: /health
            port: 80
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /
            port: 80
          periodSeconds: 10
```

**Services** (`k8s/services.yaml`):
```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: mlp-code-guardian
spec:
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: mlp-code-guardian
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 80
```

**Ingress** (`k8s/ingress.yaml`):
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mlp-ingress
  namespace: mlp-code-guardian
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - yourdomain.com
    - api.yourdomain.com
    secretName: mlp-tls
  rules:
  - host: yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 8000
```

**Secrets** (`k8s/secrets.yaml`):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mlp-secrets
  namespace: mlp-code-guardian
type: Opaque
stringData:
  redis-url: "redis://redis:6379"
  entra-tenant-id: "your-tenant-id"
  entra-client-id: "your-client-id"
```

### Deploying to Kubernetes

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (edit first!)
kubectl apply -f k8s/secrets.yaml

# Deploy services
kubectl apply -f k8s/

# Check status
kubectl get pods -n mlp-code-guardian
kubectl get services -n mlp-code-guardian

# View logs
kubectl logs -f deployment/backend -n mlp-code-guardian
```

### Helm Chart (Optional)

For more complex deployments, consider creating a Helm chart:

```bash
helm create mlp-code-guardian
# Edit values.yaml and templates as needed
helm install mlp-code-guardian ./mlp-code-guardian -n mlp-code-guardian
```

---

## API Endpoints

### Health & System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/stats` | System statistics |
| GET | `/pool-stats` | Connection pool statistics |

### Indexing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/index` | Start indexing a directory |
| GET | `/index/{index_id}/progress` | Get indexing progress |
| POST | `/index/{index_id}/stop` | Stop an indexing operation |
| GET | `/index-operations` | List all index operations |
| WS | `/ws/index/{index_id}` | Real-time indexing progress |

### Scanning

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scan` | Start similarity scan |
| GET | `/scan/{scan_id}/progress` | Get scan progress |
| GET | `/results/{scan_id}` | Get scan results |
| GET | `/scans` | List all scans |
| WS | `/ws/scan/{scan_id}` | Real-time scan progress |

### Indexed Files

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/indexed-files` | List indexed files |
| DELETE | `/indexed-files` | Delete indexed files |

### Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/config/similarity` | Get similarity settings |
| PUT | `/config/similarity` | Update similarity settings |
| POST | `/config/similarity/reset` | Reset to defaults |
| POST | `/config/similarity/preset/{level}` | Apply preset (low/medium/high) |
| GET | `/config/storage` | Get storage settings |
| PUT | `/config/storage` | Update storage backend |
| GET | `/config/storage/health` | Check storage health |
| POST | `/config/storage/test-redis` | Test Redis connection |
| GET | `/config/threading` | Get threading settings |
| PUT | `/config/threading` | Update threading settings |
| GET | `/config/ignored-files` | Get ignored patterns |
| PUT | `/config/ignored-files` | Update ignored patterns |
| POST | `/config/ignored-files/add` | Add pattern |
| DELETE | `/config/ignored-files/remove` | Remove pattern |
| POST | `/config/ignored-files/reset` | Reset to defaults |

## Tech Stack

### Backend
- FastAPI (async Python web framework)
- SQLAlchemy 2.0 (async ORM with connection pooling)
- PyJWT (JWT token validation for Entra ID)
- scikit-learn (TF-IDF vectorization and cosine similarity)
- pypdf, python-docx, openpyxl, python-pptx (document parsing)
- Redis (optional high-performance storage with hiredis)

### Frontend
- React 18
- Vite 7
- TailwindCSS 4
- MSAL React (Microsoft authentication)
- React Router 7
- Axios (HTTP client)
- Lucide React (icons)

### Infrastructure
- Docker & Docker Compose
- Nginx (reverse proxy)
- Redis 7 (optional high-performance storage)
- SQLite (default lightweight storage)

## Configuration

### Similarity Sensitivity Presets

The system supports predefined sensitivity levels for similarity matching:

| Preset | Threshold | Description |
|--------|-----------|-------------|
| `low` | ~0.75 | Fewer false positives, may miss some matches |
| `medium` | ~0.65 | Balanced detection (default) |
| `high` | ~0.55 | More matches, may have more false positives |
| `custom` | User-defined | Use individual threshold settings |

### Ignored File Patterns

Configure globally ignored files using glob patterns:
- `*.pyc`, `__pycache__/*` - Python bytecode
- `node_modules/*` - Node.js dependencies
- `.git/*`, `.svn/*` - Version control
- `*.log`, `*.tmp` - Temporary files

## License

MIT License - See LICENSE file for details.
