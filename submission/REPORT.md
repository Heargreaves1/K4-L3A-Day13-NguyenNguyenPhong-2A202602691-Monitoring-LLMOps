# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Nguyên Phong
- **MSSV:** 2A202602691
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/Heargreaves1/K4-L3A-Day13-NguyenNguyenPhong-2A202602691-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602691`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png`, `evidence/08b-trace-metadata-table.png` (cột metadata có `correlation_id`) |
| Prompt versions | `evidence/09-prompt-versions.png`, `evidence/09b-prompt-traces.png`, `evidence/09c-prompt-trace-ids.txt` |
| Prompt rollback | `evidence/10-prompt-promote.png` (production → v2), `evidence/10-prompt-rollback.png` (production → v1) |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` (khung challenge), `evidence/12b-incident-recovery.png` (sau khi tắt incident) |
| Incident log | `evidence/13-incident-log.txt` |
| Incident trace | `evidence/14-incident-trace.txt` (latency từng span của 5 trace, lấy qua Langfuse API) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (20 record thiếu `correlation_id`/enrichment) | 100/100 | Log cũ được đổi tên thành `data/logs.baseline.jsonl` trước khi đo lại |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Contract giữ nguyên; thêm dashboard runtime `scripts/build_dashboard.py` |
| `pytest` | 22 passed | 26 passed | Thêm test CCCD, thẻ, hộ chiếu, scrub payload lồng nhau |
| Số traces hợp lệ | 0 (chỉ có root observation, chưa có child) | 61 trace `day13-agent-request`; 51 trace có đủ `retrieval` + `llm-generation` | Các trace đầu được tạo trước khi thêm child observation; xem `evidence/06-trace-list.png` |
| Số PII leak | 0 (chưa có request chứa PII) | 0 (đã gửi request chứa email + SĐT) | Xem `evidence/05-pii-redaction.txt` |
| Latency P95 / TTFT P95 | ~2.5 s / 50 ms (P50 ≈ 440 ms; request đầu chậm do fetch prompt khi cache nguội) | 3,145 ms / 50 ms sau practice `rag_slow` | TTFT không đổi → nghẽn nằm trước LLM |
| Retrieval success rate | 100% | 100% | Chưa chạy `tool_fail` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` gọi `clear_contextvars()` đầu mỗi request, nhận `x-request-id` nếu hợp lệ (`[A-Za-z0-9._-]{1,64}`), nếu không thì sinh `req-<8-hex>` từ `uuid4`; bind vào structlog contextvars, lưu ở `request.state`, truyền vào `LabAgent.run` (trace metadata) và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `event`, `service`, `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id thô), `session_id`, `feature`, `model`, `env`; `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` được đăng ký sau `format_exc_info` và trước `JsonlFileProcessor`/`JSONRenderer`, scrub đệ quy mọi giá trị string (kể cả payload lồng nhau và traceback). Pattern chạy theo thứ tự thẻ → CCCD → email → SĐT VN → hộ chiếu để dãy số dài không bị cắt nhầm thành SĐT.
- **Cách kiểm chứng kết quả:** unit test trong `tests/test_pii.py`; gửi request thật chứa email + SĐT rồi kiểm tra log (`evidence/05-pii-redaction.txt`); `validate_logs.py` dùng detector độc lập, báo 0 leak.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** ảnh chụp có tên project `day13-k4-l3a-2A202602691` trên thanh điều hướng; mỗi trace có `correlation_id` trùng với log trong `data/logs.jsonl` sinh ra trên máy tôi.
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (agent) → child `retrieval` (retriever, chỉ ghi `query_preview` đã scrub và `doc_count`) → child `llm-generation` (generation, có `model`, prompt được link, `usage_details` input/output/total, `cost_details` theo đơn giá $3/$15 mỗi 1M token, metadata `ttft_ms`). Không capture raw input/output.
- **Cách nối trace với log:** `correlation_id` được đưa vào trace metadata qua `propagate_attributes`; lấy `correlation_id` từ log rồi filter metadata trên Langfuse. Ví dụ đã đối chiếu: trace `6502bf22aeaa383e1740409a9f24691b`, bắt đầu 14:59:33 (UTC+7), metadata `correlation_id=req-f3a4c6bc`, user `2f015d970c0b`, cost $0.001506, 122 tokens, khớp với log `response_sent` cùng `correlation_id` (ts 07:59:33Z, `tokens_in=27`, `tokens_out=95`, `cost_usd=0.001506`). `correlation_id` được đưa vào trace metadata qua `propagate_attributes`; lấy `correlation_id` từ log rồi filter metadata trên Langfuse để tìm trace tương ứng.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** version 1, label `baseline` (ban đầu kèm `production`); nội dung gồm 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`.
- **Version/label candidate:** version 2, label `candidate`; thêm dòng "Answer in at most 3 short bullet points." để giới hạn độ dài câu trả lời.
- **Trace ID của mỗi version:** v1/baseline: `3bca9d41720c24eaa66c7ded8b7c7ee1` (`req-b0000001`); v2/candidate: `77ca8fd1e679e0a573fd91ff2f29e994` (`req-c0000001`). Cả hai có `prompt_source=langfuse` và generation được link với đúng prompt version.
- **Cách promote và rollback `production`:** app luôn lấy prompt theo label (`LANGFUSE_PROMPT_LABEL=production`), không theo số version, nên promote/rollback chỉ là di chuyển label trên Langfuse, không cần deploy lại code. Promote: gắn `production` vào v2 (`evidence/10-prompt-promote.png`). Rollback: gắn lại `production` vào v1 (`evidence/10-prompt-rollback.png`). Kiểm tra qua API `GET /api/public/v2/prompts/day13-chat?label=production` trả về version 1 sau rollback. Lưu ý SDK cache prompt 60 s, nên cần restart hoặc chờ hết TTL thì thay đổi label mới có hiệu lực.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `python scripts/build_dashboard.py [--watch]` đọc `data/logs.jsonl` và sinh `data/dashboard.html` (time range 60 phút, refresh 30 s) gồm latency P50/P95/P99 + TTFT P95, traffic, error rate + retrieval success, cost, tokens in/out và quality; mỗi panel có đơn vị, đường threshold và nhãn trong/vượt ngưỡng (`evidence/11-dashboard-overview.png`).
- **SLO và lý do chọn:** `fast_successful_requests`: 99.5% request thành công và ≤ 3000 ms trong 28 ngày. Baseline P50 ≈ 440 ms nên ngưỡng 3000 ms có dư địa khoảng 6 lần, nhưng vẫn bắt được retrieval chậm (practice `rag_slow` đẩy P95 lên 3,145 ms).
- **Cách tính error budget:** budget = (1 − 0.995) × tổng request = 0.5%. Ví dụ 10.000 request/28 ngày → được phép 50 request lỗi hoặc chậm. Burn rate ≥ 14.4 trong 1h → page; ≥ 6 trong 6h → ticket; hết budget thì đóng băng thay đổi prompt/model.
- **Ba alert và runbook tương ứng:** `high_latency_p95` (P2, P95 > 3000 ms trong 5m), `high_error_rate` (P1, error rate > 2% trong 5m), `cost_spike` (P3, chi phí theo giờ > 2 lần baseline hoặc dự báo ngày > 2.5 USD trong 15m); tất cả gửi Slack `#day13-l3a-alerts`, runbook tại `docs/alerts.md`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 2026-09-29 09:03:47 → 09:04:02 UTC (16:03:47 → 16:04:02 giờ VN); incident `rag_slow`, seed 1311, 5 query của feature `monitoring`, concurrency 5.
- **Triệu chứng từ metrics:** panel Latency: P95 = 3,563 ms, vượt SLO 3,000 ms và ngưỡng challenge 2,000 ms (baseline P50 ≈ 440 ms). **TTFT P95 giữ nguyên 50 ms**, error rate 0%, retrieval success 100%, cost/tokens/quality bình thường. Kết luận: request chậm nhưng không lỗi, và phần chậm nằm trước khi LLM sinh token đầu tiên.
- **Log line và correlation ID liên quan:** lọc `event == "response_sent" AND feature == "monitoring" AND latency_ms > 2000` được đủ 5/5 request challenge (`req-d82235fb` 3,791 ms; `req-ba2d6a2a`, `req-a6d2bf8b`, `req-f4715ff9`, `req-9328058f` ≈ 2,652 ms), tất cả `ttft_ms=50`, `tool_success=true`. Chọn `req-a6d2bf8b` (session `k4-l3a-challenge-s03`, `latency_ms=2653`) để điều tra. Xem `evidence/13-incident-log.txt`.
- **Trace ID và span gây ảnh hưởng:** trace `e8ba040f9bd64afd37f4f99d45ba6fad` (metadata `correlation_id=req-a6d2bf8b`): `lab-agent-run` 2.655 s, trong đó **`retrieval` 2.502 s (~94%)** và `llm-generation` 0.152 s (bình thường). Cả 5 trace challenge có cùng pattern: retrieval ≈ 2.50 s, so với ≈ 0 s lúc bình thường. `req-d82235fb` chậm thêm ~1.1 s do fetch prompt lúc cache nguội.
- **Root cause:** bước retrieval (vector store / RAG) bị chậm cố định khoảng 2.5 s mỗi request (incident `rag_slow`). Metric (P95 tăng, TTFT không đổi, không có lỗi), log (5/5 request `monitoring` > 2,000 ms, `tool_success=true`) và trace (span `retrieval` chiếm ~94% thời gian) cùng chỉ về một nguyên nhân. Yếu tố làm nặng thêm: `agent.run` là hàm đồng bộ được gọi trong endpoint `async`, nên chặn event loop và các request bị xếp hàng. Phía client đo 6.4–14.4 s trong khi server chỉ ghi ~2.65 s mỗi request.
- **Fix action:** (1) đặt timeout cho retrieval (ví dụ 800 ms) và fallback trả lời không dùng context, hoặc dùng cache kết quả retrieval cho câu hỏi lặp lại; (2) kiểm tra và scale vector store (index, tài nguyên, network); (3) chạy `agent.run` trong threadpool (`await run_in_threadpool(...)`) hoặc chuyển sang client async để một request chậm không chặn các request khác. Xác minh: sau khi tắt incident, request trở về ~0.44 s (`evidence/12b-incident-recovery.png`).
- **Preventive measure:** giữ alert `high_latency_p95` (P95 > 3,000 ms trong 5 phút) và thêm alert riêng cho latency span `retrieval` (P95 > 1,000 ms), vì TTFT không đổi nên chỉ nhìn TTFT sẽ bỏ sót; ghi `retrieval_ms` vào structured log để dashboard tách được thời gian retrieval và LLM; thêm load test có concurrency vào CI để phát hiện việc chặn event loop.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** scrub PII bằng structlog processor đệ quy đặt trước mọi bước render/ghi file, thay vì scrub ở từng chỗ gọi log, để mọi field mới (kể cả exception detail) tự động được bảo vệ.
- **Một lỗi/blocker đã gặp:** (1) Tạo v2 có tick `production` nên label bị chuyển khỏi v1, và `baseline`/`candidate` chưa tồn tại, khiến chạy theo label sẽ rơi về template local. (2) Sau rollback, request `req-e0000001` (trace `0bd98bbe7ac32d75eac8133a78af82a7`) có `prompt_source=local-fallback`, `prompt_fetch_error=LangfuseFallback`: request đầu tiên sau khi restart server fetch prompt vượt `fetch_timeout_seconds=2` (không retry).
- **Cách tìm nguyên nhân và xử lý:** (1) Đọc lại danh sách version, gắn đúng `baseline`+`production` cho v1 và `candidate` cho v2, rồi xác nhận qua metadata trace (`prompt_version` 1/2, `prompt_source=langfuse`). (2) Đọc metadata trace qua Langfuse API v2 và gọi trực tiếp `GET /api/public/v2/prompts/day13-chat?label=production` → 200, version 1, nên label đúng, lỗi chỉ là timeout lúc cold start. Không tăng timeout vì test công khai khóa giá trị này; thay vào đó gửi một request làm nóng sau khi restart. Fallback cũng cho thấy thiết kế đúng: Langfuse chậm không làm request lỗi mà metadata ghi rõ nguồn prompt.
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời "có vấn đề gì và từ khi nào" nhưng là số tổng hợp, không chỉ ra request cụ thể. Logs trả lời "request nào bị ảnh hưởng": lọc theo khoảng thời gian và điều kiện (ví dụ `latency_ms > 2000`) để lấy `correlation_id`. Traces trả lời "bước nào gây ra": cùng `correlation_id` nằm trong trace metadata, nên mở được waterfall và thấy span nào chiếm thời gian hoặc có lỗi. Ở challenge: P95 tăng nhưng TTFT không đổi (metrics) → 5/5 request `monitoring` > 2 s (logs) → span `retrieval` 2.5 s / 2.65 s (trace). Kết luận chỉ hợp lệ khi cả ba cùng chỉ về một nguyên nhân.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** với LLM, thay prompt cũng là một lần "deploy" có thể làm đổi chất lượng, độ dài output và chi phí; gắn `prompt_version` vào mọi trace giúp biết chính xác request nào chạy prompt nào. App lấy prompt theo label nên rollback chỉ là chuyển label `production` về version cũ, không cần deploy lại code. Token/cost phải theo dõi như một SLI vì output dài hơn (ví dụ `cost_spike`) làm tăng chi phí mà không sinh lỗi. SLO + error budget biến "hệ thống chậm" thành con số để quyết định lúc nào dừng thay đổi prompt/model và ưu tiên sửa độ tin cậy.
- **Điều quan trọng nhất đã học:** observability phải được thiết kế từ đầu: correlation ID xuyên suốt log và trace, PII bị che trước khi ghi, và mỗi bước quan trọng là một span riêng. Nếu chỉ có root span thì trace chỉ báo "request chậm" mà không biết chậm ở đâu. Ngoài ra, xem nhiều tín hiệu cùng lúc (latency tăng nhưng TTFT không đổi) giúp khoanh vùng nhanh trước cả khi mở trace.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** (1) chưa có ảnh chụp waterfall của trace incident; thay bằng dữ liệu span lấy qua Langfuse API (`evidence/14-incident-trace.txt`), có thể mở trace `e8ba040f9bd64afd37f4f99d45ba6fad` trên Langfuse để kiểm tra. (2) Trace sau promote (`req-d0000001`) chưa được tạo, và trace sau rollback `req-e0000001` rơi vào local-fallback do timeout lúc cold start; promote/rollback được chứng minh bằng ảnh label và API prompt. (3) Chưa sửa việc `agent.run` đồng bộ chặn event loop (chỉ đề xuất trong fix action). (4) Dashboard là HTML tĩnh sinh từ log, không phải Grafana; TTFT chưa được gửi vào trường `completion_start_time` của Langfuse nên cột TTFT trên Langfuse trống.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
