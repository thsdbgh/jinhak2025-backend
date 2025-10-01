# app.py  — Production-ready (Render + Supabase REST only)
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from datetime import datetime

# env 파일은 로컬 개발 때만; Render에선 환경변수로 주입
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Flask 기본 설정 ---
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # 한글 깨짐 방지
# 배포 후 Netlify 도메인으로 제한 권장: ["https://<your-netlify>.netlify.app"]
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Supabase REST 클라이언트 ---
from supabase import create_client
from postgrest.exceptions import APIError as PostgrestAPIError

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # anon key 사용
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_KEY 환경변수가 필요합니다.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 유틸 ---
REQUIRED_ATTENDEE_FIELDS = [
    "name", "grade", "class", "number", "parent_phone", "attendance_type"
]

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

# --- Routes ---
@app.get("/")
def home():
    return {"ok": True, "service": "jinhak2025-backend", "ts": now_iso()}

@app.get("/health/db")
def health_db():
    try:
        res = supabase.table("notices").select("id").limit(1).execute()
        return {"db": "ok", "mode": "supabase-py", "rows": len(res.data)}
    except Exception as e:
        return {"db": "error", "detail": str(e)}, 500

@app.post("/checkin")
def check_in():
    """현장 체크인"""
    if supabase:
        data = request.json
        student_id = data.get("student_id")  # 학번 기반 확인

        res = supabase.table("attendees") \
            .update({"checked_in": True}) \
            .eq("student_id", student_id) \
            .execute()

        if res.data:
            return jsonify({"status": "ok", "message": "체크인 완료"})
        else:
            return jsonify({"status": "error", "message": "해당 학생 없음"}), 404
    else:
        return jsonify({"status": "error", "message": "DB 연결 안됨"}), 500


@app.get("/notices")
def get_notices():
    """공지사항 목록 (핀 고정 우선, 최신순) — anon SELECT 허용 필요"""
    try:
        res = (
            supabase.table("notices")
            .select("*")
            .order("pinned", desc=True)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(res.data)
    except PostgrestAPIError as e:
        return jsonify({"status": "error", "detail": e.args[0]}), 400
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

@app.post("/attendees")
def add_attendee():
    """참석자 신청 — anon INSERT 허용 필요 (SELECT 불허 상태 가정)"""
    data = request.get_json(silent=True) or {}

    # 필수값 검증
    for f in REQUIRED_ATTENDEE_FIELDS:
        if data.get(f) in (None, ""):
            return jsonify({"status": "error", "message": f"{f} is required"}), 400

    # 선택값은 빈 문자열 허용 (NOT NULL 제약 우회)
    payload = {
        "name": data.get("name"),
        "grade": data.get("grade"),
        "class": data.get("class"),
        "number": data.get("number"),
        "student_phone": data.get("student_phone") or "",
        "parent_phone": data.get("parent_phone"),
        "attendance_type": data.get("attendance_type"),
        "extra_notes": data.get("extra_notes") or "",
    }

    try:
        # returning="minimal" → INSERT 후 SELECT 생략(SELECT RLS 없어도 됨)
        supabase.table("attendees").insert(payload, returning="minimal").execute()
        return jsonify({"status": "ok"})
    except PostgrestAPIError as e:
        return jsonify({"status": "error", "detail": e.args[0]}), 400
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    # 로컬 개발 서버 (Render에서는 gunicorn이 실행)
    app.run(host="0.0.0.0", port=5000)
