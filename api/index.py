"""
api/index.py
Vercel Python(서버리스) 엔트리포인트.

Vercel 은 vercel.json 의 builds 설정에 따라 이 파일의 `app` 객체를
WSGI 애플리케이션으로 사용한다. 로컬 실행은 루트의 app.py 를 그대로 쓰면 된다.
"""

import os
import sys

# 루트 디렉토리를 import 경로에 추가 (app.py, models.py 로드용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401
