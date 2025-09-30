# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os

# env 파일(.env) 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# 두 가지 접근 방식 지원
# 1) 로컬 개발: supabase-py (HTTPS, 방화벽 이슈 회피)
from supabase import create_client
from postgrest.exceptions import APIError as PostgrestAPIError

# 2) 배포/운영: psycopg2 (Postgres 직결)
import psycopg2

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
# 배포 후에는 origins=["https://<당신의 Netlify 도메인>"] 처럼 제한하세요.
CORS(app, resources={r"/*": {"origins": "*"}})

# 환경변수
DATABASE_URL = os.environ.get("DATABASE_URL")        # 배포/운영용
SUPABASE_URL = os.environ.get("SUPABASE_URL")        # 로컬용
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")        # 로컬용 (anon key 권장)

# supabase-py 클라이언트 (로컬 모드에서 사용)
supabase = None
if SUPABASE_URL and SUPABASE_KEY and not DATABASE_URL:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# psycopg2 연결 (배포/운영 모드)
def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)

@app.get("/")
def home():
    return {"ok": True, "service": "jinhak2025-backend"}

@app.get("/health/db")
def health_db():
    try:
        if DATABASE_URL:
            # 운영 모드: DB 직결 확인
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.fetchone()
            cur.close()
            conn.close()
            return {"db": "ok", "mode": "psycopg2"}
        elif supabase:
            # 로컬 모드: REST로 간단 조회
            res = supabase.table("notices").select("id").limit(1).execute()
            return {"db": "ok", "mode": "supabase-py", "rows": len(res.data)}
        else:
            return {"db": "error", "detail": "No DB config found"}, 500
    except Exception as e:
        return {"db": "error", "detail": str(e)}, 500

@app.post("/attendees")
def add_attendee():
    """참석자 신청 등록
    필수: name, grade, class, number, parent_phone, attendance_type
    선택: student_phone, extra_notes
    """
    data = request.json or {}
    required = ["name", "grade", "class", "number", "parent_phone", "attendance_type"]
    for f in required:
        if data.get(f) in (None, ""):
            return jsonify({"status": "error", "message": f"{f} is required"}), 400

    # 운영 모드: psycopg2 (직결)
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO attendees
                  (name, grade, class, number, student_phone, parent_phone, attendance_type, extra_notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    data.get("name"),
                    data.get("grade"),
                    data.get("class"),
                    data.get("number"),
                    data.get("student_phone"),
                    data.get("parent_phone"),
                    data.get("attendance_type"),
                    data.get("extra_notes"),
                ),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"status": "ok", "id": new_id})
        except Exception as e:
            return jsonify({"status": "error", "detail": str(e)}), 500

    # 로컬 모드: supabase-py (HTTP)
    elif supabase:
        try:
            # returning="minimal" 로 하면 PostgREST가 INSERT 후 SELECT를 안 해서
            # attendees 테이블 SELECT 정책 없이도 RLS에 안 걸립니다.
            supabase.table("attendees").insert(
                {
                    "name": data.get("name"),
                    "grade": data.get("grade"),
                    "class": data.get("class"),
                    "number": data.get("number"),
                    "student_phone": data.get("student_phone"),
                    "parent_phone": data.get("parent_phone"),
                    "attendance_type": data.get("attendance_type"),
                    "extra_notes": data.get("extra_notes"),
                },
                returning="minimal",
            ).execute()
            return jsonify({"status": "ok"})
        except PostgrestAPIError as e:
            # Supabase(PostgREST) 에러 원문 노출 (디버깅 편의용)
            return jsonify({"status": "error", "detail": e.args[0]}), 400
        except Exception as e:
            return jsonify({"status": "error", "detail": str(e)}), 500

    else:
        return jsonify({"status": "error", "message": "No DB config found"}), 500

@app.get("/notices")
def get_notices():
    """공지사항 목록"""
    # 운영 모드: psycopg2
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, title, content, pinned, created_at
                FROM notices
                ORDER BY pinned DESC, created_at DESC
                """
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify(
                [
                    {
                        "id": r[0],
                        "title": r[1],
                        "content": r[2],
                        "pinned": r[3],
                        "created_at": r[4].isoformat() if r[4] else None,
                    }
                    for r in rows
                ]
            )
        except Exception as e:
            return jsonify({"status": "error", "detail": str(e)}), 500

    # 로컬 모드: supabase-py
    elif supabase:
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

    else:
        return jsonify({"status": "error", "message": "No DB config found"}), 500

if __name__ == "__main__":
    # 로컬 개발 서버
    app.run(debug=True, host="0.0.0.0", port=5000)
