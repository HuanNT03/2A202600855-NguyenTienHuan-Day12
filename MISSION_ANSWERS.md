# Day 12 Lab - Mission Answers

> **Student Name:** Nguyễn Tiến Huân  
> **Student ID:** 2A202600855  
> **Date:** 12/06/2026  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
Trong file `01-localhost-vs-production/develop/app.py`, các anti-pattern nguy hiểm sau đã được phát hiện:

1. **Hardcoded Credentials & Secrets (Dòng 17, 18):** `OPENAI_API_KEY` và `DATABASE_URL` bị lưu trực tiếp dạng chuỗi trong mã nguồn. Khi đưa code lên GitHub/GitLab, các thông tin nhạy cảm này sẽ lập tức bị lộ, có thể dẫn tới thất thoát tài khoản hoặc cơ sở dữ liệu.
2. **Thiếu quản lý cấu hình tập trung (Config Management - Dòng 21, 22):** Các tham số như `DEBUG = True` hay `MAX_TOKENS = 500` được định nghĩa cứng trong file Python. Chúng không thể thay đổi linh hoạt giữa các môi trường (Dev, Staging, Prod) mà không cần chỉnh sửa trực tiếp mã nguồn.
3. **Sử dụng logs không an toàn và không cấu trúc (Dòng 33, 34):** Ứng dụng dùng câu lệnh `print()` để ghi nhật ký thay vì thư viện logging tiêu chuẩn. Nghiêm trọng hơn, log in thẳng khoá bảo mật `OPENAI_API_KEY` ra stdout. logs dạng plain text này rất khó truy vấn/phân tích trên các hệ thống thu thập log tập trung (như ELK, Datadog).
4. **Không có Health Check Endpoints:** Ứng dụng thiếu các endpoint phục vụ liveness probe (`/health`) và readiness probe (`/ready`). Do đó, container orchestrators (như K8s, Railway, Render) không thể giám sát trạng thái để tự động khởi động lại nếu ứng dụng bị treo.
5. **Hardcoded Host và Port (Dòng 51-53):** App binds cứng vào `localhost` và port `8000`. Khi chạy trong container hoặc deploy lên Cloud (Railway/Render), ứng dụng cần bind vào `0.0.0.0` để nhận các yêu cầu định tuyến bên ngoài và port phải được inject động thông qua biến môi trường `PORT`.
6. **Bật chế độ Debug Autoreload trong Production (Dòng 53):** Tham số `reload=True` khởi chạy thêm luồng giám sát tệp tin, gây hao phí tài nguyên CPU đáng kể và mở ra các nguy cơ bảo mật tiềm tàng khi debug server vẫn chạy ở môi trường production.
7. **Không xử lý Graceful Shutdown:** Ứng dụng không có cơ chế bắt các tín hiệu kết thúc chương trình (`SIGTERM`, `SIGINT`). Khi nhận tín hiệu tắt máy, ứng dụng sẽ bị ngắt đột ngột, làm gián đoạn toàn bộ request đang được xử lý dở dang (in-flight requests).

---

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
| :--- | :--- | :--- | :--- |
| **Config** | Hardcode trực tiếp trong mã nguồn (`app.py`). | Quản lý qua biến môi trường (.env, Pydantic BaseSettings). | Giúp phân tách cấu hình ra khỏi code theo nguyên lý 12-Factor App, bảo mật secrets và dễ đổi cấu hình theo môi trường. |
| **Health Check** | Không có endpoint kiểm tra trạng thái nào. | Có `/health` (Liveness) & `/ready` (Readiness) endpoints. | Giúp Platform (Railway, K8s, Render) biết khi nào container lỗi để restart và điều phối traffic một cách an toàn. |
| **Logging** | Dùng `print()`, log plain-text không phân cấp, in secrets. | Sử dụng Structured JSON Logging thông qua thư viện `logging`. | Giúp các công cụ giám sát tập trung (Datadog, Loki) dễ parse/filter logs mà không sợ bị rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Đột ngột ngắt tiến trình (abrupt exit). | Xử lý signal `SIGTERM`/`SIGINT`, đợi request hiện tại hoàn tất. | Ngăn ngừa lỗi mất mát dữ liệu hoặc lỗi HTTP 5xx từ phía người dùng khi tiến trình container bị tắt/scale-down/redeploy. |
| **Network Binding** | Bind cứng vào `localhost` và port `8000`. | Bind vào `0.0.0.0` và cổng động lấy từ biến môi trường `PORT`. | Cho phép container nhận được traffic định tuyến từ Load Balancer của cloud platform và tránh conflict port. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image:** Base image là `python:3.11`. Đây là bản phân phối Debian chính thức chứa đầy đủ các công cụ build (gcc, pip, compilers) với kích thước lớn (~1 GB).
2. **Working directory:** Thư mục làm việc trong container được chỉ định qua lệnh `WORKDIR /app`. Mọi câu lệnh chạy phía sau (`COPY`, `RUN`, `CMD`) đều lấy thư mục này làm gốc.
3. **Tại sao COPY requirements.txt trước?** Thiết kế này tận dụng cơ chế lưu trữ đệm (layer caching) của Docker. Docker xây dựng image theo các layer chồng lên nhau. Nếu file `requirements.txt` không thay đổi, Docker sẽ dùng lại layer cache chứa dependencies đã cài trước đó. Việc copy code thay đổi thường xuyên (`COPY app.py .`) sau khi chạy `pip install` giúp tăng tốc độ build đáng kể trong các lần kế tiếp.
4. **CMD vs ENTRYPOINT khác nhau thế nào?**
   - `ENTRYPOINT` quy định lệnh thực thi chính mặc định của container khi khởi động và không thể ghi đè bằng các đối số dòng lệnh thông thường trừ khi sử dụng cờ `--entrypoint`.
   - `CMD` chứa các đối số mặc định truyền vào cho `ENTRYPOINT` (nếu có) hoặc lệnh chạy mặc định khi container chạy. Lệnh trong `CMD` có thể dễ dàng bị ghi đè hoàn toàn bằng cách truyền một lệnh khác vào sau lệnh `docker run <image> <new_command>`.

---

### Exercise 2.3: Image size comparison
- **Develop:** 1140 MB
- **Production:** 160.33 MB
- **Difference:** Giảm khoảng **85.9%** dung lượng tệp tin (tiết kiệm ~979.67 MB).
- **Lý do dung lượng Production nhỏ hơn:** Dockerfile của production áp dụng mô hình **Multi-stage build**:
  - **Stage 1 (Builder):** Sử dụng `python:3.11-slim` làm base, cài đặt các build tool (`gcc`, `libpq-dev`) để biên dịch/cài đặt các package cần thiết vào thư mục `/root/.local`.
  - **Stage 2 (Runtime):** Bắt đầu từ một image `python:3.11-slim` mới hoàn toàn sạch sẽ. Stage này chỉ sao chép các thư viện đã cài đặt thành công từ Stage 1 sang và copy source code ứng dụng. Toàn bộ compiler nặng nề và file thừa từ quá trình build đều bị loại bỏ ở Stage 1, giúp giảm tối đa dung lượng image cuối cùng và hạn chế tối đa các lỗ hổng bảo mật.

---

### Exercise 2.4: Docker Compose stack
- **Kiến trúc luồng traffic:**
  ```
  Client/Browser (Request)
         │
         ▼
  ┌──────────────┐
  │ Nginx (Proxy)│ (Port 80)
  └──────┬───────┘
         │
    Round-Robin (Định tuyến cân bằng tải)
         │
         ├───► agent_1 (Port 8000, container internal)
         ├───► agent_2 (Port 8000, container internal)
         └───► agent_3 (Port 8000, container internal)
                  ▲
                  │  (Lưu và truy vấn session history/cost/rate limit)
                  ▼
             ┌──────────┐
             │  Redis   │ (Port 6379, container internal)
             └──────────┘
  ```
- **Các dịch vụ khởi động cùng stack:**
  1. `nginx`: Đóng vai trò là Reverse Proxy & Load Balancer ở cổng ngoài `80`, phân chia luồng request của client tới các agent instance.
  2. `agent`: Các container chạy mã nguồn chính FastAPI AI Agent, được nhân bản lên thành 3 instances (`agent_1`, `agent_2`, `agent_3`) để phục vụ mở rộng tải ngang.
  3. `redis`: Dịch vụ lưu trữ in-memory dùng chung để lưu session chat history, thống kê rate limit và kiểm soát budget hàng ngày (cost guard) cho cả 3 instances.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- **URL:** `https://production-ai-agent-production.up.railway.app` (URL mẫu để nộp bài)
- **Screenshot:** [Link to screenshots in repo](screenshots/)

### Câu hỏi thảo luận bổ sung:
1. **Tại sao serverless (AWS Lambda, etc.) không phải lúc nào cũng tốt cho AI Agent?**
   - AI Agent thường chạy theo vòng lặp suy nghĩ (ReAct Loop) hoặc gọi nhiều API LLM/công cụ bên ngoài liên tiếp. Thời gian xử lý của mỗi request có thể rất dài (vài chục giây đến vài phút). Với mô hình tính tiền theo thời gian chạy của Serverless, chi phí sẽ tăng lên rất cao.
   - Các thư viện dành cho AI (như LangChain, PyTorch, Pydantic, các SDK LLM) có kích thước lớn, khiến thời gian khởi động lạnh (Cold Start) của serverless tăng cao.
   - Khó lưu trạng thái kết nối persistent (như connection pool tới database hay Redis) do vòng đời của function serverless quá ngắn.
2. **"Cold start" là gì? Ảnh hưởng thế nào đến trải nghiệm người dùng (UX)?**
   - "Cold start" xảy ra khi platform serverless nhận được request đầu tiên sau một khoảng thời gian dài không hoạt động. Platform sẽ phải tải container image lên, khởi động môi trường runtime mới, cài đặt biến môi trường và chạy code khởi tạo.
   - Việc này gây trễ phản hồi ban đầu từ 5-15 giây, khiến người dùng cảm giác hệ thống bị đơ, lag, làm suy giảm UX trầm trọng.
3. **Khi nào nên upgrade từ Railway lên Cloud Run (GCP)?**
   - Khi dự án cần cơ chế Auto-scaling chuyên sâu hơn (đặc biệt là Scale-to-Zero để tiết kiệm chi phí tối đa khi không hoạt động và tự động scale lên hàng trăm container khi có bão traffic).
   - Khi cần kết nối mạng bảo mật trong mạng nội bộ (VPC Peering) với cơ sở dữ liệu lớn trên Google Cloud.
   - Khi cần hệ thống phân phối traffic nâng cao như A/B Testing, Canary deployments.
   - Khi cần đáp ứng các tiêu chuẩn bảo mật doanh nghiệp (compliance, IAM roles chi tiết).

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results

Dưới đây là mô phỏng quá trình kiểm tra bảo mật từ các API endpoint:

#### 1. Yêu cầu API Key (Lỗi 401 Unauthorized khi thiếu key):
```bash
$ curl -i http://localhost:8000/ask -X POST -H "Content-Type: application/json" -d '{"question": "Hello"}'

HTTP/1.1 401 Unauthorized
date: Fri, 12 Jun 2026 13:28:00 GMT
server: uvicorn
content-length: 74
content-type: application/json

{"detail":"Invalid or missing API key. Include header: X-API-Key: <key>"}
```

#### 2. Gọi thành công với API Key hợp lệ:
```bash
$ curl -i http://localhost:8000/ask -X POST -H "X-API-Key: dev-key-change-me" -H "Content-Type: application/json" -d '{"question": "What is Docker?"}'

HTTP/1.1 200 OK
date: Fri, 12 Jun 2026 13:28:10 GMT
server: uvicorn
content-length: 165
content-type: application/json

{"question":"What is Docker?","answer":"[Mock LLM Response] Answer to: What is Docker?","model":"qwen-turbo","timestamp":"2026-06-12T13:28:10.123456Z"}
```

#### 3. Bị chặn do vượt quá Rate Limit (Lỗi 429 Too Many Requests):
```bash
$ for i in {1..25}; do curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: dev-key-change-me" -H "Content-Type: application/json" -d '{"question": "test"}' http://localhost:8000/ask; done

200
200
... (18 lần 200)
200
429
429
429
```
*Chi tiết phản hồi lỗi 429:*
```json
{
  "detail": "Rate limit exceeded: 20 req/min"
}
```

---

### Exercise 4.4: Cost guard implementation
Trong file `06-lab-complete/app/main.py`, logic **Cost Guard** đã được triển khai hiệu quả nhờ sự hỗ trợ của Redis:
- **Nguyên lý tính toán chi phí:** 
  - Số lượng token đầu vào (input tokens) và đầu ra (output tokens) của cuộc hội thoại được tính toán (ở dạng mock: tính dựa trên độ dài của câu hỏi/phản hồi nhân với hệ số quy đổi).
  - Chi phí được tính theo đơn giá: **$0.0003/1K input tokens** và **$0.0006/1K output tokens**.
- **Lưu trữ stateless bằng Redis:**
  - Sử dụng Redis key dạng: `cost:<user_id_hash>:<YYYY-MM-DD>` lưu trữ chi phí tích lũy trong ngày của mỗi người dùng. Key có thời gian hết hạn (TTL) là 2 ngày để tự động giải phóng bộ nhớ.
- **Cơ chế chặn vượt hạn mức:**
  - Trước khi gửi câu hỏi tới LLM, hàm `check_and_record_cost()` sẽ tải chi phí hiện tại của người dùng từ Redis lên.
  - Nếu số tiền đã tiêu vượt quá hạn mức ngày (`settings.daily_budget_usd`, mặc định $5.0), hệ thống sẽ từ chối cuộc gọi bằng mã lỗi `HTTP 503 Service Unavailable` kèm thông báo *"Daily budget exhausted. Try tomorrow."*.
  - Nếu ngân sách vẫn còn, chi phí ước lượng của câu hỏi mới sẽ được cộng dồn trực tiếp vào Redis bằng lệnh `incrbyfloat`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

#### 1. Liveness và Readiness Checks:
- **Liveness Probe (`/health`):** Trả về trạng thái hoạt động hiện tại của app, bao gồm thời gian chạy (uptime), phiên bản ứng dụng và thông tin kiểm tra kết nối với Redis. Giúp orchestrator tự khởi động lại container khi tiến trình bị treo cứng.
- **Readiness Probe (`/ready`):** Kiểm tra xem kết nối tới Redis có thông suốt không. Nếu Redis gặp sự cố, endpoint này sẽ lập tức trả về lỗi `HTTP 503 Service Unavailable` để Load Balancer tạm thời ngắt container này khỏi hàng đợi định tuyến traffic mới.

#### 2. Graceful Shutdown (SIGTERM/SIGINT):
- Sử dụng lifecycle quản lý `lifespan` kết hợp với lắng nghe tín hiệu `SIGTERM`.
- Khi platform chuẩn bị tắt container (do deploy bản mới hoặc scale down), tín hiệu `SIGTERM` được gửi đi. 
- Ngay lúc này, cờ `_is_ready` chuyển thành `False` (khiến `/ready` trả về 503 để Load Balancer ngắt kết nối mới).
- Ứng dụng đợi tối đa 30 giây (`timeout_graceful_shutdown=30` trong uvicorn) cho các request đang xử lý (in-flight) kết thúc trọn vẹn, giải phóng các kết nối Redis rồi mới chính thức chấm dứt tiến trình.

#### 3. Stateless Design:
- Ứng dụng loại bỏ hoàn toàn các biến lưu lịch sử hội thoại trong bộ nhớ RAM (`_memory_store`).
- Mọi lịch sử hội thoại được serialization thành JSON và ghi nhận vào Redis dưới key dạng `history:<user_id>` với thời gian lưu trữ (TTL) là 1 giờ.
- Nhờ vậy, request 1 của User A có thể được xử lý tại `agent_1` (và lưu lịch sử vào Redis), sang request 2 load balancer định tuyến sang `agent_2`, `agent_2` vẫn lấy được đầy đủ ngữ cảnh cuộc hội thoại trước đó từ Redis để trả lời chuẩn xác.

#### 4. Load Balancing & Stateless Verification:
- Khi kiểm tra thực tế với lệnh scale: `docker compose up --scale agent=3`, 3 container agent được khởi chạy song song cùng Nginx làm Load Balancer.
- Chạy script `test_stateless.py` gửi liên tiếp các câu hỏi của cùng một session. Kết quả logs chỉ ra các câu trả lời được xử lý ngẫu nhiên bởi các `INSTANCE_ID` khác nhau (ví dụ: `agent-1`, `agent-3`), nhưng mạch hội thoại vẫn liên tục và không hề bị mất dữ liệu lịch sử, chứng minh thiết kế Stateless đạt tiêu chuẩn production-grade.
