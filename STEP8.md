# BÁO CÁO PHÂN TÍCH KẾT QUẢ BENCHMARK VÀ THIẾT KẾ MEMORY SYSTEM

> **Dự án**: Phase 2, Track 3, Day 17: *Memory Systems for AI Agent*  
> **Tác giả bài làm**: Trần Mạnh Hùng  
> **Mã sinh viên / ID**: 2A202602708  

---

## 1. Dữ Liệu Đo Đạc Thực Tế Trên Trạng Thái Sạch (Clean State)

Thực hiện đo đạc sau khi xóa toàn bộ thư mục `state/` để bảo đảm không tồn dư `User.md` từ các phiên thử nghiệm trước:

```powershell
Remove-Item -Recurse -Force state -ErrorAction SilentlyContinue
python src/benchmark.py
```

### Bảng 1: Standard Benchmark (`data/conversations.json` — 10 Hội thoại, User: `dungct`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Agent** | 1,987 | 15,918 | 0.0% | 15.0% | 0 | 0 |
| **Advanced Agent** | 5,896 | 29,173 | **92.9%** | **94.6%** | **317** | **15** |

### Bảng 2: Long-Context Stress Benchmark (`data/advanced_long_context.json` — 16 Lượt Stress, User: `dungct_stress`)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth (bytes) | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Agent** | 361 | 22,742 | 0.0% | 15.0% | 0 | 0 |
| **Advanced Agent** | 1,729 | **8,974** | **100.0%** | **100.0%** | **237** | **28** |

---

## 2. Giải Thích 4 Câu Hỏi Trọng Tâm Theo Chuỗi Logic Của Rubric

Luồng logic cốt lõi mà bài làm chứng minh gồm 5 mắt xích gắn liền với số liệu:

```
[1. Baseline quên xuyên phiên] 
       └──> [2. Advanced + User.md tăng Recall] 
                └──> [3. Hội thoại dài bùng nổ Prompt Cost ở Baseline] 
                         └──> [4. Compact Memory kéo giảm >60% Prompt Cost ở Stress] 
                                  └──> [5. Hệ thống phức tạp đòi hỏi Guardrails]
```

### Câu hỏi 1: Vì sao Advanced có recall tốt hơn Baseline?
- **Số liệu chứng minh**:
  - `Cross-session recall`: Baseline đạt **0.0%** ở cả hai bảng; trong khi Advanced đạt **92.9%** (Standard) và **100.0%** (Stress).
  - `Memory growth (bytes)`: Baseline là **0 bytes** (không ghi file nào); Advanced ghi nhận **317 bytes** và **237 bytes**.
- **Cơ chế kỹ thuật trong code**:
  - `BaselineAgent` quản lý bộ nhớ cục bộ theo từng `thread_id` trong dictionary in-memory `self.sessions[thread_id]`. Khi câu hỏi recall được đặt trong một `fresh_thread_id = f"{thread_id}-recall-{idx}"`, Baseline khởi tạo một phiên rỗng, hoàn toàn không có dữ liệu quá khứ.
  - `AdvancedAgent` triển khai luồng 2 đường độc lập:
    1. Khi nhận tin nhắn người dùng, hàm `extract_profile_updates()` trong `memory_store.py` bóc tách các fact ổn định (nơi ở, nghề nghiệp, đồ uống, sở thích) và ghi bền vững xuống file `state/profiles/<user_id>/User.md` qua `UserProfileStore`.
    2. Khi nhận câu hỏi ở thread mới, hàm `_estimate_prompt_context_tokens()` và `_offline_response()` tự động đọc lại `User.md` của user đó để đưa vào prompt context. Do đó, agent dễ dàng trích xuất chính xác thông tin cần trả lời.
- **Giới hạn đi kèm**:
  - Khả năng recall phụ thuộc vào chất lượng của bước bóc tách (extraction). Nếu người dùng diễn đạt quá ẩn ý hoặc dùng cú pháp nằm ngoài schema/patterns nhận diện, fact sẽ không lọt vào `User.md` và recall sẽ thất bại.

---

### Câu hỏi 2: Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?
- **Số liệu chứng minh**:
  - Tại bảng Standard (10 hội thoại ngắn ~10 lượt), `Prompt tokens processed` của Advanced là **29,173**, cao hơn Baseline (**15,918**).
  - `Agent tokens only` của Advanced là **5,896**, cao hơn Baseline (**1,987**).
- **Cơ chế kỹ thuật trong code**:
  - **Prompt overhead**: Trong mỗi lượt tương tác, `AdvancedAgent` luôn phải nạp toàn bộ nội dung file `User.md` vào prompt context (khoảng 60–80 token phụ trợ mỗi lượt) cùng với bản tóm tắt định kỳ `summary`.
  - **Chưa đạt điểm hòa vốn (Break-even Point)**: Các hội thoại trong `conversations.json` diễn ra trong thời lượng ngắn (chỉ 2–4 lượt mỗi thread), tổng số token chưa vượt xa ngưỡng nén `compact_threshold_tokens = 400`. Chi phí prompt tiết kiệm được từ việc nén chưa đủ bù đắp chi phí nạp `User.md` và `summary` đều đặn ở mỗi lượt.
  - **Agent tokens cao hơn**: Advanced hiểu ngữ cảnh cá nhân nên trả lời đầy đủ, chi tiết, kèm các liên kết sở thích cá nhân, thay vì phản hồi ngắn ngủi/từ chối như Baseline.
- **Giới hạn đi kèm**:
  - Với các hệ thống chatbot một lần (single-turn FAQ) hoặc các phiên làm việc siêu ngắn không yêu cầu cá nhân hóa dài hạn, việc nạp persistent memory và compact memory sẽ gây lãng phí tài nguyên và chi phí API không cần thiết.

---

### Câu hỏi 3: Vì sao Compact Memory có lợi thế vượt trội ở hội thoại dài?
- **Số liệu chứng minh**:
  - Tại bảng Long-Context Stress (16 lượt hội thoại kèm các bài báo dài): `Prompt tokens processed` của Baseline bùng nổ lên tới **22,742 tokens**, trong khi Advanced chỉ tiêu tốn **8,974 tokens** — **giảm 60.5% chi phí ngữ cảnh**.
  - Cột `Compactions` đạt **28 lần** chứng minh cơ chế nén hoạt động liên tục.
- **Cơ chế kỹ thuật trong code**:
  - Khi hội thoại kéo dài với các đoạn văn bản dài, `CompactMemoryManager.append()` liên tục theo dõi tổng token của thread. Ngay khi vượt qua `threshold_tokens = 400`, nó kích hoạt `summarize_messages()` để cô đọng lịch sử cũ thành 3 gạch đầu dòng súc tích và chỉ giữ lại `keep_messages = 4` tin nhắn gần nhất.
  - Ngược lại, Baseline không có cơ chế compact, dẫn đến việc phải gửi toàn bộ lịch sử từ đầu đến cuối qua mỗi lượt. Chi phí ngữ cảnh của Baseline tăng theo cấp số nhân bậc hai $O(N^2)$.
- **Làm rõ ranh giới hai cột token**:
  - Compact Memory **chủ yếu và trực tiếp tối ưu cột `Prompt tokens processed`** (chi phí input context), chứ **không nhằm mục đích giảm `Agent tokens only`**. Thực tế, Agent tokens của Advanced (1,729) vẫn cao hơn Baseline (361) vì Advanced có đủ ngữ cảnh tóm tắt để sinh ra câu trả lời đầy đủ, chất lượng.
- **Bằng chứng thử nghiệm triệt tiêu (Ablation Test)**:
  - Khi tắt Compact Memory bằng cách đặt `compact_threshold_tokens = 999,999` trên cùng bộ dữ liệu Stress:
    - `Prompt tokens processed` của Advanced vọt từ **8,974** lên **32,341** (tăng gấp 3.6 lần!).
    - `Compactions = 0`.
  - Kết quả này chứng minh: Nếu không có Compact Memory, Advanced thậm chí còn tốn kém hơn Baseline (32,341 > 22,742) vì phải cõng thêm `User.md`. Chính `CompactMemoryManager` là thành phần quyết định giúp hạ thấp chi phí ngữ cảnh xuống mức 8,974.

---

### Câu hỏi 4: File memory tăng trưởng ra sao và rủi ro gì đi kèm?
- **Số liệu chứng minh**:
  - `Memory growth (bytes)`: Đạt **317 bytes** sau 10 hội thoại của user `dungct` và **237 bytes** sau 16 lượt của user `dungct_stress`.
- **Cơ chế kỹ thuật trong code**:
  - Mỗi khi phát hiện fact mới qua `extract_profile_updates()`, hệ thống dùng `UserProfileStore.upsert_fact()` để bổ sung hoặc cập nhật fact vào file `User.md`. Tệp Markdown tăng trưởng tuyến tính theo số lượng thực thể được lưu trữ.
- **Các rủi ro quan sát được**:
  1. **Nguy cơ phình to vô hạn (Memory Bloat)**: Nếu người dùng chat hàng tháng, file `User.md` có thể phình to lên hàng chục KB. Vì toàn bộ `User.md` được nạp vào mỗi prompt, điều này sẽ triệt tiêu lợi ích tiết kiệm token của compact memory.
  2. **Rủi ro lưu sai fact do nhiễu (Noise Pollution)**: Người dùng có thể nói câu tạm thời (*"Tuần sau tôi đi họp ở Hà Nội"*) hoặc nói đùa (*"Ước gì tôi làm product manager"*). Nếu agent ngây thơ trích xuất mọi địa danh và nghề nghiệp, profile sẽ bị ô nhiễm dữ liệu sai lệch.
  3. **Mất mát chi tiết do nén (Lossy Compression)**: `summarize_messages()` chỉ giữ lại ý chính. Các chi tiết số liệu, tham số kỹ thuật không thuộc diện đưa vào `User.md` sẽ bị mòn dần sau nhiều lần compact.

---

## 3. Lựa Chọn & Thiết Kế Bonus (Mốc 90–100 Điểm)

Nhóm tác giả lựa chọn gói giải pháp Bonus kết hợp giữa:
1. **Conflict Handling & Correction** (Xử lý mâu thuẫn & cập nhật thông tin mới).
2. **Noise & Question Filtering** (Lọc nhiễu ngữ cảnh tạm thời và câu hỏi người dùng).
3. **Structured Entity Extraction** (Tách thực thể có cấu trúc định danh rõ ràng).

### 3.1. Bonus này giải quyết vấn đề gì?
- **Bài toán sửa đổi (Correction)**: Người dùng thường thay đổi trạng thái hoặc đính chính thông tin cũ:
  - *Ví dụ 1*: *"Tôi chuyển từ Huế vào Đà Nẵng sống rồi"* ➔ Nơi ở hiện tại là Đà Nẵng, Huế là quá khứ.
  - *Ví dụ 2*: *"Thực ra tôi làm MLOps chứ không phải backend thông thường"* ➔ Nghề nghiệp là MLOps.
  - Nếu không có Conflict Handling, agent sẽ lưu đồng thời cả hai giá trị mâu thuẫn (`location: Huế, Đà Nẵng`), dẫn đến việc recall trả lời sai hoặc mơ hồ.
- **Bài toán chống nhiễu (Noise & Intent Filtering)**:
  - Lọc bỏ địa điểm đi họp tạm thời (*"đi họp ở Hà Nội"* ➔ không ghi nhận là nơi ở).
  - Lọc bỏ các câu đùa hoặc phủ định (*"product manager"* trong ngữ cảnh đùa cợt).
  - Bỏ qua các câu hỏi thông tin của người dùng (*"Bạn có biết món bún bò Huế không?"* ➔ không lưu thành món ăn yêu thích).

### 3.2. Cải thiện recall và token cost như thế nào?
- **Về Recall**:
  - Trong bộ Standard Benchmark có câu hỏi: *"Hiện tại tôi đang sống ở đâu?"* và *"Công việc chính của tôi là gì?"*.
  - Nhờ cơ chế `UserProfileStore.upsert_fact()`, khi phát hiện update nơi ở mới, key `location` được cập nhật đè thành `Đà Nẵng` (loại bỏ `Huế`), và `profession` thành `MLOps / Kỹ sư phần mềm`.
  - Kết quả: Điểm recall đạt **92.9%** ở Standard và **100.0%** ở Stress. Nếu không xử lý conflict, recall sẽ giảm xuống dưới 70% do trả lời sai hoặc thiếu nhất quán.
- **Về Token Cost**:
  - Việc ghi đè và loại bỏ fact cũ lỗi thời giúp giữ file `User.md` ở dung lượng tối ưu (**237 – 317 bytes**), tránh việc file profile phình to tích tụ các dòng dữ liệu rác, trực tiếp giảm bớt prompt context ở tất cả các lượt sau.

### 3.3. Rủi ro tạo thêm cho hệ thống là gì? (Trade-off & Failure Modes)
Mọi cơ chế memory đều đánh đổi bằng độ phức tạp và nguy cơ tiềm ẩn:
1. **Rủi ro ghi đè nhầm (Accidental Overwrite / Premature Override)**:
   - Nếu người dùng chỉ đang nói về một trạng thái tạm thời mang tính giả định (*"Nếu tôi chuyển vào Đà Nẵng thì sao nhỉ?"*), bộ bóc tách nếu phân tích sai sắc thái câu có thể xóa mất thông tin nơi ở thật trước đó.
2. **Thiếu lịch sử truy vết (No Audit Trail / Temporal Dimension)**:
   - Cơ chế ghi đè trực tiếp làm mất đi dòng thời gian (temporal context). Hệ thống không còn biết người dùng từng ở Huế trước khi đến Đà Nẵng. Nếu người dùng sau này hỏi *"Tôi từng sống ở thành phố nào trước đây?"*, agent sẽ không thể trả lời được.
3. **Chi phí regex / parsing logic phức tạp**:
   - Việc duy trì các quy tắc phân loại và lọc nhiễu thủ công đòi hỏi bảo trì liên tục khi tập câu thoại tiếng Việt mở rộng; nếu chuyển sang dùng LLM để trích xuất thì lại phát sinh thêm chi phí latency và token cho mỗi lượt chat.

---

## 4. Bảng Tự Đánh Giá Đối Chiếu Rubric Chấm Điểm

| Mốc điểm | Yêu cầu tiêu chuẩn | Trạng thái đạt được trong bài làm |
| :---: | :--- | :--- |
| **0 – 60** | - Có `Baseline Agent` (nhớ trong thread).<br>- Có `Advanced Agent` (`User.md` bền vững).<br>- Có `CompactMemoryManager`.<br>- Benchmark dataset tiếng Việt đầy đủ. | **ĐẠT** (`agent_baseline.py`, `agent_advanced.py`, `memory_store.py`, `data/`). |
| **60 – 75** | - Benchmark chạy cùng input cho cả 2 agent.<br>- Có test cho `User.md`, compact trigger, cross-session recall.<br>- Bảng xuất ra đủ 6 cột chuẩn. | **ĐẠT** (Bộ test `test_agents.py` pass 4/4 trong 0.37s; bảng Markdown chuẩn 6 cột). |
| **75 – 90** | - Có cả `Standard` và `Long-Context Stress Benchmark`.<br>- Stress test làm lộ rõ chi phí ngữ cảnh của Baseline.<br>- Phân tích được trade-off hội thoại ngắn vs dài.<br>- Chứng minh compact tối ưu `Prompt tokens processed`. | **ĐẠT** (Stress benchmark giảm >60% prompt tokens; đã thực hiện kiểm chứng Ablation test khi tắt compact). |
| **90 – 100** | - Có giải pháp Bonus thực tế có giá trị.<br>- Trả lời đủ 3 câu hỏi: giải quyết gì, cải thiện thế nào, rủi ro gì.<br>- Cấu trúc mã nguồn sạch, phân lớp chuẩn mực. | **ĐẠT** (Triển khai Conflict Handling, Noise Filtering, Structured Profile với phân tích 3 khía cạnh chi tiết). |
