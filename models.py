"""
models.py
R&D 사업 제안요청서(RFP) 분석 시스템 - SQLite 데이터베이스 모델 정의
"""

import json
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# --------------------------------------------------------------------------
# 1) 분석 이력 테이블
# --------------------------------------------------------------------------
class AnalysisHistory(db.Model):
    """RFP 분석 1건의 전체 기록 (원문 + 분석결과 JSON)"""

    __tablename__ = "analysis_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(255), nullable=False, default="직접 입력 문서")
    project_title = db.Column(db.String(500), nullable=False, default="(사업명 미기재)")
    raw_text = db.Column(db.Text, nullable=False, default="")
    result_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    # ---- 편의 프로퍼티 -------------------------------------------------
    @property
    def result(self):
        """분석결과 JSON 문자열 -> dict"""
        try:
            return json.loads(self.result_json or "{}")
        except (TypeError, ValueError):
            return {}

    @result.setter
    def result(self, value):
        self.result_json = json.dumps(value, ensure_ascii=False)

    def to_summary(self):
        """사이드바 히스토리 목록용 경량 dict"""
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.project_title,
            "date": self.created_at.strftime("%m/%d %H:%M"),
        }

    def to_dict(self):
        """상세 조회용 전체 dict"""
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.project_title,
            "date": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "rawText": self.raw_text,
            "data": self.result,
        }

    def __repr__(self):
        return f"<AnalysisHistory {self.id} {self.project_title[:20]!r}>"


# --------------------------------------------------------------------------
# 2) 설정(Key-Value) 테이블
# --------------------------------------------------------------------------
class Settings(db.Model):
    """연구소 역량 등 애플리케이션 설정값을 담는 Key-Value 저장소"""

    __tablename__ = "settings"

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # ---- 헬퍼 ---------------------------------------------------------
    @staticmethod
    def get(key, default=""):
        row = db.session.get(Settings, key)
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = db.session.get(Settings, key)
        if row:
            row.value = value
        else:
            row = Settings(key=key, value=value)
            db.session.add(row)
        db.session.commit()
        return row

    def __repr__(self):
        return f"<Settings {self.key}>"


# --------------------------------------------------------------------------
# 기본 역량 설정값 (최초 1회 시딩)
# --------------------------------------------------------------------------
SETTING_KEY_CAPABILITIES = "tta_capabilities"

DEFAULT_CAPABILITIES = """[TTA SW시험인증연구소 핵심 역량]
- 인증제도: GS인증, CC인증, 정보보호제품 성능평가
- 시험분야: SW 품질(ISO/IEC 25000), AI 신뢰성 및 성능, 데이터 품질, 보안성, 상호운용성
- 인프라: AI 전문 테스트베드, 5G/네트워크 테스트 장비 보유, KOLAS 국제공인시험기관
- 표준화: ITU-T, ISO/IEC 국제표준 참여, TTA 단체표준 제정
- 강점: 공공/민간 대규모 R&D 품질 검증 전담 기관 경험 다수, 제3자 독립적 검증 가능"""


def init_db(app):
    """테이블 생성 + 기본 설정값 시딩"""
    with app.app_context():
        db.create_all()
        if db.session.get(Settings, SETTING_KEY_CAPABILITIES) is None:
            db.session.add(
                Settings(key=SETTING_KEY_CAPABILITIES, value=DEFAULT_CAPABILITIES)
            )
            db.session.commit()
