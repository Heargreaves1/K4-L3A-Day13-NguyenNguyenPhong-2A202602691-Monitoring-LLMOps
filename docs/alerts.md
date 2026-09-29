# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Quy trình điều tra chung: **Metrics → Logs → Traces**.

## Alert 1

- Tên: `high_latency_p95`
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (99.5% request thành công và ≤ 3000 ms trong 28 ngày)
- Điều kiện và thời gian duy trì: P95 `latency_ms` của `response_sent` > 3000 ms liên tục 5 phút
- Ảnh hưởng tới người dùng: câu trả lời chậm, error budget của SLO bị tiêu nhanh
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel Latency: P95/P99 tăng từ lúc nào; TTFT có tăng không (TTFT bình thường → nghẽn nằm trước LLM, tức retrieval/prompt fetch).
  2. Lọc `data/logs.jsonl` các `response_sent` có `latency_ms > 3000`, lấy `correlation_id`.
  3. Mở trace Langfuse có cùng `correlation_id`, so sánh thời lượng span `retrieval` và `llm-generation`.
- Mitigation tạm thời: nếu `retrieval` chậm, giảm top-k/timeout retrieval hoặc bật cache; nếu LLM chậm, chuyển sang model nhỏ hơn; rollback deploy/prompt gần nhất nếu trùng thời điểm.
- Owner: Nguyen Nguyen Phong

## Alert 2

- Tên: `high_error_rate`
- Severity: P1
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests`; guardrail `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `request_failed / request_received` > 2% liên tục 5 phút
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel Errors: breakdown theo `error_type` và retrieval success rate (`tool_success`).
  2. Lọc log `event == "request_failed"`, xem `error_type`, `tool_name`, `payload.detail` và lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`: span nào có level ERROR (ví dụ `retrieval` → vector store timeout).
- Mitigation tạm thời: nếu lỗi ở retrieval, trả lời fallback không dùng context/tạm tắt RAG; retry có backoff; nếu do deploy mới thì rollback.
- Owner: Nguyen Nguyen Phong

## Alert 3

- Tên: `cost_spike`
- Severity: P3
- Duration: 15m
- Kênh thông báo: Slack `#day13-l3a-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: chi phí theo giờ > 2 lần baseline hoặc dự báo chi phí ngày > 2.5 USD, kéo dài 15 phút
- Ảnh hưởng tới người dùng: không ảnh hưởng ngay, nhưng vượt ngân sách; câu trả lời dài bất thường có thể giảm chất lượng
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel Cost và Tokens: tăng do `tokens_in` (prompt/context phình) hay `tokens_out` (output dài), hay do traffic tăng.
  2. Lọc log `response_sent` có `tokens_out` cao, lấy `correlation_id`, kiểm tra `feature`/`model`.
  3. Mở trace cùng `correlation_id`: xem usage/cost của `llm-generation` và `prompt_version` đang dùng.
- Mitigation tạm thời: giới hạn `max_tokens`, rollback label `production` về prompt version trước nếu prompt mới gây output dài, rate-limit feature gây tốn kém.
- Owner: Nguyen Nguyen Phong
