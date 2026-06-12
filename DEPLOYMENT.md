# Deployment Information

> **Student Name:** Nguyễn Tiến Huân  
> **Student ID:** 2A202600855  
> **Date:** 12/06/2026  

---

## Public URL
https://production-ai-agent-production.up.railway.app

## Platform
Railway

---

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
curl -i https://production-ai-agent-production.up.railway.app/health
```
**Expected Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 124.5,
  "total_requests": 1,
  "checks": {
    "llm": "qwen-turbo",
    "redis": "connected"
  },
  "timestamp": "2026-06-12T13:30:00Z"
}
```

### 2. Readiness Probe Check
```bash
curl -i https://production-ai-agent-production.up.railway.app/ready
```
**Expected Response:**
```json
{
  "ready": true
}
```

### 3. API Test (Missing API Key - Expected 401)
```bash
curl -i -X POST https://production-ai-agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```
**Expected Response:**
```json
{
  "detail": "Invalid or missing API key. Include header: X-API-Key: <key>"
}
```

### 4. API Test (With API Key - Expected 200)
```bash
curl -i -X POST https://production-ai-agent-production.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
```
**Expected Response:**
```json
{
  "question": "What is the capital of France?",
  "answer": "[Mock LLM Response] Answer to: What is the capital of France?",
  "model": "qwen-turbo",
  "timestamp": "2026-06-12T13:30:10.123456Z"
}
```

### 5. Rate Limiting Test (Expected 429 after exceeding limit)
```bash
for i in {1..25}; do 
  curl -s -H "X-API-Key: dev-key-change-me" -X POST -H "Content-Type: application/json" \
    -d '{"question": "Test limit"}' https://production-ai-agent-production.up.railway.app/ask \
    | grep -o "Rate limit exceeded" || echo "200 OK"; 
done
```

---

## Environment Variables Set

Các biến môi trường cấu hình trên Railway Dashboard để chạy ứng dụng ở chế độ production:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Cổng dịch vụ lắng nghe (Railway tự động ánh xạ và định tuyến). |
| `ENVIRONMENT` | `production` | Bật chế độ chạy chính thức của hệ thống (Production). |
| `HOST` | `0.0.0.0` | Bind vào tất cả các interface mạng để nhận request ngoài. |
| `AGENT_API_KEY` | `dev-key-change-me` | API Key dùng để authenticate các request gửi lên `/ask`. |
| `REDIS_URL` | `redis://default:password@your-redis-host:6379/0` | URL kết nối tới Redis instance (Stateful storage). |
| `DAILY_BUDGET_USD` | `5.0` | Hạn mức chi tiêu tối đa hàng ngày cho LLM token. |
| `RATE_LIMIT_PER_MINUTE` | `20` | Giới hạn số lượng request tối đa trong 1 phút (20 req/min). |

---

## Screenshots
Các ảnh chụp màn hình minh chứng được đặt tại thư mục `screenshots/` của repository:
- **Deployment Dashboard:** [dashboard.png](screenshots/dashboard.png) - Trạng thái ứng dụng chạy ổn định trên giao diện quản trị của Railway.
- **Service Running:** [running.png](screenshots/running.png) - Logs ứng dụng ghi nhận các event `startup`, `redis_connected` và `ready`.
- **Test Results:** [test.png](screenshots/test.png) - Kết quả chạy thành công các lệnh kiểm tra `curl` từ môi trường localhost tới Cloud URL.
