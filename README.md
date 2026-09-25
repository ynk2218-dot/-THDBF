# 강의 영상 → 학습 자료 5종 생성기

유튜브 링크나 강의 영상 파일을 넣으면 **학습 자료 5종**을 Markdown과 인쇄용 PDF로 만들어 줍니다.

| 파일 | 역할 | 학습 단계 |
|---|---|---|
| `01_정리본` | 핵심 질문 · 목차 · 개념 카드(정의→왜 필요한가→작동 원리→예시→흔한 오해) · 개념 관계도 | **이해** |
| `02_필기본` | 코넬 노트 [단서 질문 \| 필기 \| 요약] — 필기 칸을 가리고 설명해 보기 | **재구성** |
| `03_필사본` | 핵심 문장 10~15개 따라 쓰기 + 내 말로 바꿔 쓰기 (영어 강의는 끊어읽기 포함) | **재구성** |
| `04_워크북` | 빈칸 · 원인-결과 연결 · 백지 설명 · 새 상황 적용 · 자신감 체크 | **인출·검증** |
| `05_문제지` + `05_정답해설` | 기본/응용/심화 문항 + 오답마다 원인 태그 [개념 미이해] [적용 실패] [용어 혼동] [부주의] | **적용·진단** |

> 👉 결과물 예시는 [`samples/`](samples/) 폴더에 있습니다. PDF를 바로 열어 보세요.

---

## 어떻게 작동하나 (왜 이렇게 만들었나)

```
 /study <링크 또는 파일>
      │
      ▼
 ① 전처리 (Python)       — 자막 다운로드(수동 > 자동) → 없으면 음성 인식(faster-whisper)
      │                      → transcript_raw.md(타임스탬프) + transcript_clean.md(읽기용)
      ▼
 ② 구조 분석 (Claude)     — analysis.md: 핵심 질문 · 목차 · 개념 · 개념 간 인과 관계 · 강조점
      │
      ▼
 ③ 5종 자료 (Claude)      — 모두 analysis.md 한 곳을 기준으로 작성 → 자료끼리 설명이 어긋나지 않음
      │
      ▼
 ④ 자동 검수 → PDF 변환    — 타임스탬프·문항 수 확인 → A4 PDF (문제지는 2단)
```

- **기계적인 일은 Python**(다운로드·음성 인식·PDF), **이해가 필요한 일은 Claude Code**(분석·자료 작성)가 맡습니다.
  별도의 API 키나 비용이 들지 않습니다. 평소 쓰는 Claude Code 안에서 돌아갑니다.
- 강의에 없는 내용은 지어내지 않고, 보충 설명에는 **[보충]** 배지가 붙습니다.
- 핵심 주장마다 **근거 타임스탬프** `[03:12]`가 붙습니다. 유튜브 강의면 PDF에서 누르면 그 장면으로 이동합니다.

---

## 설치 (처음 한 번만, 약 10분)

> 명령어는 **터미널**에 한 줄씩 복사해서 붙여 넣고 Enter 를 누르면 됩니다.
> - Mac: `Spotlight(⌘+Space)` → "터미널" 검색
> - Windows: 시작 메뉴 → "PowerShell" 검색
>
> 🍎 표시는 Mac, 🪟 표시는 Windows 전용 명령입니다. 표시가 없으면 둘 다 같습니다.

### 1단계. 준비물 확인

**Python** (3.10 이상)
```bash
python3 --version     # 🍎
py --version          # 🪟
```
`Python 3.10` 이상이 나오면 통과입니다. 오류가 나면 https://www.python.org/downloads/ 에서 설치하세요.
(🪟 설치 화면 첫 페이지에서 **"Add python.exe to PATH"** 에 꼭 체크)

**ffmpeg** (영상에서 소리를 꺼내는 도구)
```bash
brew install ffmpeg          # 🍎  (brew 가 없다면 https://brew.sh 의 첫 줄 명령을 먼저 실행)
winget install ffmpeg        # 🪟  (설치 후 PowerShell 을 껐다가 다시 여세요)
```

**Claude Code** — 이미 쓰고 계시면 통과입니다.

### 2단계. 이 프로젝트 내려받기
```bash
git clone https://github.com/ynk2218-dot/-THDBF.git study-tool
cd study-tool
```
(git 이 없다면: GitHub 페이지의 초록색 **Code → Download ZIP** 으로 받아 압축을 풀고, 터미널에서 `cd ` 뒤에 그 폴더를 끌어다 놓고 Enter)

### 3단계. 전용 파이썬 환경 만들고 부품 설치
이 프로젝트만 쓰는 공간(.venv)을 만들어 그 안에 설치합니다. 컴퓨터의 다른 프로그램에 영향을 주지 않습니다.

🍎 Mac
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

🪟 Windows
```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```
> 세 번째 줄은 PDF를 만들 브라우저를 받는 명령입니다(약 150MB).
> 컴퓨터에 Chrome 이나 Edge 가 이미 있으면 실패해도 괜찮습니다. 자동으로 그걸 씁니다.

### 4단계. 설치 점검
```bash
.venv/bin/python scripts/doctor.py            # 🍎
.venv\Scripts\python.exe scripts\doctor.py    # 🪟
```
모든 줄이 ✅ 이면 끝입니다. ❌ 가 있으면 그 아래 **→ 해결** 에 적힌 명령을 실행하세요.

---

## 사용법

### 1. 프로젝트 폴더에서 Claude Code 켜기
```bash
cd study-tool      # 2단계에서 받은 폴더
claude
```

### 2. `/study` 명령 입력
```
/study https://www.youtube.com/watch?v=XXXXXXXX
```

로컬 영상 파일도 됩니다. 경로에 공백이 있으면 **큰따옴표**로 감싸 주세요.
```
/study "/Users/나/Downloads/3강 수요와 공급.mp4"                # 🍎
/study "C:\Users\나\Downloads\3강 수요와 공급.mp4"              # 🪟
```
> 💡 파일 경로를 직접 치기 어렵다면, 터미널 창에 파일을 **끌어다 놓으면** 경로가 자동으로 입력됩니다.

### 3. 옵션
| 옵션 | 뜻 | 예 |
|---|---|---|
| `--lang ko` / `--lang en` | 강의 언어 지정 (생략하면 자동 감지) | `/study <링크> --lang en` |
| `--level 기본` / `--level 심화` | 자료 난이도. 심화는 문항 수↑, 심화 문항 비율↑, 경계 조건·반례 추가 | `/study <링크> --level 심화` |
| `--material 파일` | 강의 교재·자료 함께 넣기 (아래 설명). 여러 개면 반복 | `/study <링크> --material "교재.pdf"` |

### 교재 함께 넣기 (`--material`)
이 도구는 강의의 **소리**만 분석합니다. 그래서 강사가 **화면에만 띄우고 읽지 않은** 문제 원문·예문·표는 자료에 빠집니다.
교재를 함께 넣으면 그 빈 곳을 교재에서 찾아 채웁니다.

```
/study https://youtu.be/XXXX --material "C:\Users\user\Downloads\3강 교재.pdf"
/study "강의.mp4" --material "교재.pdf" --material "판서 사진.jpg"
```
- 지원 형식: **PDF**(글자 PDF·스캔본 모두), **사진**(jpg, png), txt/md
- 한글(hwp)·워드(docx)는 **다른 이름으로 저장 → PDF**로 바꿔서 넣어 주세요.
- 교재에서 가져온 내용에는 **`[교재 p.12]`** 배지가 붙습니다(PDF 쪽 번호 기준).
- 강의에서 다루지 않은 교재 내용은 넣지 않습니다. 이 자료는 **이 강의**를 이해하기 위한 것이라서요.
- 교재에서도 찾지 못한 것은 지어내지 않고 **`[확인 불가]`**로 표시합니다.
- 두꺼운 교재 전체를 넣어도 되지만, **해당 강의 부분만** 잘라 넣으면 더 빠르고 정확합니다.

### 4. 결과 확인
`output/날짜_강의제목/` 폴더에 생깁니다.
```
output/2026-09-25_강의제목/
├── 01_정리본.md / .pdf
├── 02_필기본.md / .pdf
├── 03_필사본.md / .pdf
├── 04_워크북.md / .pdf
├── 05_문제지.md / .pdf       ← 2단 편집, 정답 없음
├── 05_정답해설.md / .pdf     ← 별도 파일
├── analysis.md              ← 자료의 설계도 (개념·인과 관계·강조점)
└── _source/                 ← 전사본(원본·정제본), 영상 정보
```

### 5. 추천 학습 순서
1. **정리본**으로 큰 그림(원인 → 과정 → 결과) 이해
2. **필기본** 필기 칸을 가리고 단서 질문에 답해 보기 / **필사본** 따라 쓰고 내 말로 바꾸기
3. **워크북**은 자료를 덮고 풀기. 마지막 자신감 체크가 가장 중요합니다
4. **문제지** 풀고 채점 → 해설 끝의 **오답 기록표**에 원인 태그 기록 → 태그별 처방 따라 복습

---

## 새 버전으로 업데이트하기
**가장 쉬운 방법**: `study-tool` 폴더에서 Claude Code를 켜고 이렇게 입력하세요.
```
https://github.com/ynk2218-dot/-THDBF 의 최신 코드로 이 폴더를 업데이트해 줘. output 폴더와 .venv 폴더는 건드리지 말고, 끝나면 requirements.txt 로 패키지도 다시 설치해 줘.
```

**직접 하는 방법** (🪟 Windows)
1. GitHub에서 ZIP을 다시 받아 압축을 풉니다.
2. 풀린 폴더 안의 파일을 전부 선택해서 `study-tool` 폴더에 **덮어쓰기**로 붙여 넣습니다. `output`, `.venv`는 새 ZIP에 없으므로 그대로 남습니다.
3. PowerShell에서:
```powershell
cd ~\study-tool
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 설정 바꾸기 (`config.yaml`)
메모장이나 VS Code 로 열어 숫자만 바꾸면 됩니다.

| 항목 | 뜻 | 기본값 |
|---|---|---|
| `materials.문제지.total` | 문항 수 | 15 |
| `materials.문제지.types` | 객관식·단답·서술형 개수 | 8 · 4 · 3 |
| `materials.문제지.difficulty` | 기본·응용·심화 비율(%) | 40 · 40 · 20 |
| `materials.필사본.min/max_sentences` | 필사 문장 수 | 10~15 |
| `materials.워크북.*` | 워크북 유형별 문항 수 | |
| `level_overrides.심화` | `--level 심화` 일 때 바뀌는 값 | |
| `whisper.model` | 음성 인식 정확도 (tiny < base < small < medium < large-v3) | small |
| `long_lecture.threshold_min` | 이 길이(분) 이상이면 구간을 나눠 분석 | 40 |
| `output_language` | 자료를 쓸 언어 | ko |

---

## 자주 겪는 문제

| 화면에 나온 메시지 | 원인 | 해결 |
|---|---|---|
| `[LOGIN_OR_DRM]` 로그인·구매가 필요한 영상 | 유료 인강·비공개·회원 전용 영상 | 영상 파일을 직접 받아 `/study "파일경로"` 로 넣기 |
| `[LOGIN_OR_DRM]` 지원하지 않는 사이트 | 유료 인강 사이트 대부분 | 위와 같음 |
| `[LOGIN_OR_DRM]` 로봇이 아닌지 확인 | YouTube 의 자동 접속 차단 | `config.yaml` 의 `cookies_from_browser` 에 `chrome` 등 브라우저 이름 입력 |
| `[LOGIN_OR_DRM]` 파일이 암호화(DRM)… | 인강 앱 전용 파일 | 일반 플레이어에서 재생되는 mp4 등으로 받기 |
| `[MISSING_TOOL]` ffmpeg | ffmpeg 미설치 | 설치 1단계 참고 |
| `[MODEL_DOWNLOAD]` | 첫 음성 인식 때 모델(약 500MB)을 못 받음 | 인터넷 확인 후 재실행 |
| `[NETWORK]` | 인터넷 끊김, 회사·학교망 차단 | 다른 네트워크에서 시도하거나 파일로 넣기 |
| 유튜브에서 오디오가 안 받아짐 | yt-dlp 가 유튜브 변경을 못 따라감 | `.venv/bin/python -m pip install -U yt-dlp` (🪟 `.venv\Scripts\python.exe -m pip install -U yt-dlp`). 그래도 안 되면 `brew install deno` / `winget install DenoLand.Deno` |
| PDF 생성 실패 | 브라우저 없음 | 설치 3단계의 `playwright install chromium` 재실행 |

> **자막 파일이 따로 있다면**: 영상과 **같은 이름**의 `.srt`/`.vtt` 파일을 같은 폴더에 두면 음성 인식 대신 그 자막을 씁니다(더 빠르고 정확).
> 자막 파일만 넣어도 됩니다: `/study "강의.srt"`

---

## 알아 두면 좋은 한계
- **자동 자막·음성 인식은 전문 용어를 틀리게 받아 적을 수 있습니다.** Claude가 문맥으로 교정하고, 그 내역을 `analysis.md` 10번 항목에 남깁니다. 중요한 시험 대비라면 한 번 훑어보세요.
- 강의가 화면(판서·슬라이드)에만 보여 주고 **말로 하지 않은 내용**은 자료에 들어가지 않습니다(소리만 분석합니다).
- 음성 인식 시간: 5분 강의 ≈ 1~3분, 1시간 강의 ≈ 15~40분 (컴퓨터 성능과 `whisper.model` 에 따라 다름).

---

## 폴더 구조 (궁금한 분만)
```
.claude/commands/study.md   /study 명령의 작업 지시서 (Claude가 따르는 순서)
guides/                     자료별 작성 규칙 — 교육 설계의 핵심. 고치면 자료 스타일이 바뀜
scripts/preprocess.py       전처리 (다운로드·자막·음성 인식·정제·구간 분할)
scripts/render_pdf.py       Markdown → PDF
scripts/check_materials.py  자동 검수 (타임스탬프 실재 여부·문항 수·태그)
scripts/doctor.py           설치 점검
templates/*.css             PDF 디자인 (공통 / 코넬 노트 / 2단 문제지)
config.yaml                 분량·난이도·언어 설정
```
