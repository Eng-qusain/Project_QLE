"""
project_QLE/database/db.py
──────────────────────────
SQLAlchemy ORM models and database management.

Stores: Projects, Wells, Petrophysics, Formation Tops, DST Tests, ML Models, Results
"""
from __future__ import annotations
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import json

# ── Database setup ──────────────────────────────────────────
DB_PATH = os.path.expanduser("~/.project_qle/database.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Session = sessionmaker(bind=ENGINE)
Base = declarative_base()


# ── ORM Models ──────────────────────────────────────────────

class Project(Base):
    """A project/profile for organizing wells and analyses."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    basin = Column(String(50), nullable=False)  # SIRTE, GHADAMES, etc.
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    wells = relationship("Well", back_populates="project", cascade="all, delete-orphan")
    interpretations = relationship("Interpretation", back_populates="project", cascade="all, delete-orphan")
    ml_models = relationship("MLModel", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project {self.name} ({self.basin})>"


class Well(Base):
    """A well log with petrophysical data."""
    __tablename__ = "wells"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    well_name = Column(String(255), nullable=False)
    uwi = Column(String(100), default="")
    field_name = Column(String(255), default="")
    latitude = Column(Float)
    longitude = Column(Float)
    kb_elevation = Column(Float)
    td_depth = Column(Float)
    start_depth = Column(Float)
    stop_depth = Column(Float)
    step = Column(Float)
    las_file_path = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="wells")
    petro_data = relationship("PetroData", back_populates="well", cascade="all, delete-orphan")
    formation_tops = relationship("FormationTop", back_populates="well", cascade="all, delete-orphan")
    dst_tests = relationship("DSTTest", back_populates="well", cascade="all, delete-orphan")
    interpretations = relationship("Interpretation", back_populates="well", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Well {self.well_name}>"


class PetroData(Base):
    """Petrophysical calculations at each depth level."""
    __tablename__ = "petro_data"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    depth_m = Column(Float, nullable=False)
    gr = Column(Float)
    rhob = Column(Float)
    nphi = Column(Float)
    rt = Column(Float)
    dt = Column(Float)
    vshale = Column(Float)
    phie = Column(Float)  # effective porosity
    sw = Column(Float)    # water saturation
    sh = Column(Float)    # hydrocarbon saturation
    perm_md = Column(Float)
    pore_pressure_psi = Column(Float)
    facies = Column(String(100))

    well = relationship("Well", back_populates="petro_data")

    def __repr__(self):
        return f"<PetroData depth={self.depth_m}m>"


class FormationTop(Base):
    """Formation top picks for a well."""
    __tablename__ = "formation_tops"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    formation_name = Column(String(255), nullable=False)
    depth_m = Column(Float, nullable=False)
    lithology = Column(String(100))  # Sandstone, Shale, Limestone, etc.
    description = Column(Text, default="")
    confidence = Column(Float, default=0.5)  # 0-1 confidence level
    picked_at = Column(DateTime, default=datetime.utcnow)

    well = relationship("Well", back_populates="formation_tops")

    def __repr__(self):
        return f"<FormationTop {self.formation_name} @ {self.depth_m}m>"


class DSTTest(Base):
    """Drill Stem Test data."""
    __tablename__ = "dst_tests"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    test_name = Column(String(255), nullable=False)
    depth_m = Column(Float, nullable=False)
    duration_hours = Column(Float)
    initial_shut_in_psi = Column(Float)
    final_shut_in_psi = Column(Float)
    flow_rate_bpd = Column(Float)
    api_gravity = Column(Float)
    gor_scfbbl = Column(Float)
    permeability_md = Column(Float)
    skin_factor = Column(Float)
    reservoir_pressure_psi = Column(Float)
    temperature_f = Column(Float)
    fluid_type = Column(String(50))  # Oil, Gas, Water
    description = Column(Text, default="")
    test_date = Column(DateTime)

    well = relationship("Well", back_populates="dst_tests")

    def __repr__(self):
        return f"<DSTTest {self.test_name}>"


class Interpretation(Base):
    """Saved interpretations and summaries."""
    __tablename__ = "interpretations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    well_id = Column(Integer, ForeignKey("wells.id"))
    interpretation_type = Column(String(50))  # 'petrophysics', 'reservoir', 'trend', etc.
    summary = Column(Text)
    ai_narrative = Column(Text)
    porosity_summary = Column(JSON)  # {mean, std, p10, p50, p90}
    permeability_summary = Column(JSON)
    saturation_summary = Column(JSON)  # {sw_mean, sh_mean, sg_mean}
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="interpretations")
    well = relationship("Well", back_populates="interpretations")

    def __repr__(self):
        return f"<Interpretation {self.interpretation_type}>"


class MLModel(Base):
    """Trained machine learning models and performance metrics."""
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    model_name = Column(String(100), nullable=False)  # 'linear_regression', 'random_forest', 'xgboost'
    target_variable = Column(String(100))  # what the model predicts (e.g. 'porosity', 'permeability')
    input_features = Column(JSON)  # list of feature column names
    mae = Column(Float)  # mean absolute error
    rmse = Column(Float)  # root mean squared error
    r2_score = Column(Float)
    training_samples = Column(Integer)
    model_bytes = Column(Text)  # pickled model as base64 string
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, default="")

    project = relationship("Project", back_populates="ml_models")

    def __repr__(self):
        return f"<MLModel {self.model_name} r2={self.r2_score:.3f}>"


# ── Database initialization ─────────────────────────────────

def init_database():
    """Create all tables."""
    Base.metadata.create_all(ENGINE)


def get_session():
    """Get a new database session."""
    return Session()


# ── Helper functions ────────────────────────────────────────

def create_project(name: str, basin: str, description: str = "") -> Project:
    """Create and save a new project."""
    session = get_session()
    try:
        proj = Project(name=name, basin=basin, description=description)
        session.add(proj)
        session.commit()
        return proj
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_project(name: str) -> Project | None:
    """Retrieve a project by name."""
    session = get_session()
    try:
        return session.query(Project).filter_by(name=name).first()
    finally:
        session.close()


def list_projects() -> list[Project]:
    """List all projects."""
    session = get_session()
    try:
        return session.query(Project).all()
    finally:
        session.close()


def delete_project(name: str) -> bool:
    """Delete a project and all associated data."""
    session = get_session()
    try:
        proj = session.query(Project).filter_by(name=name).first()
        if proj:
            session.delete(proj)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def save_well(project_id: int, well_name: str, las_path: str, **kwargs) -> Well:
    """Save a well to the database."""
    session = get_session()
    try:
        well = Well(
            project_id=project_id,
            well_name=well_name,
            las_file_path=las_path,
            **kwargs
        )
        session.add(well)
        session.commit()
        return well
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_wells_in_project(project_id: int) -> list[Well]:
    """Get all wells in a project."""
    session = get_session()
    try:
        return session.query(Well).filter_by(project_id=project_id).all()
    finally:
        session.close()


def save_petro_data_batch(well_id: int, data_list: list[dict]):
    """Bulk-save petrophysical data."""
    session = get_session()
    try:
        for data in data_list:
            petro = PetroData(well_id=well_id, **data)
            session.add(petro)
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def save_formation_top(well_id: int, formation_name: str, depth_m: float,
                       lithology: str = "", description: str = "") -> FormationTop:
    """Save a formation top."""
    session = get_session()
    try:
        top = FormationTop(
            well_id=well_id,
            formation_name=formation_name,
            depth_m=depth_m,
            lithology=lithology,
            description=description,
        )
        session.add(top)
        session.commit()
        return top
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def save_dst_test(well_id: int, test_name: str, depth_m: float, **kwargs) -> DSTTest:
    """Save a DST test."""
    session = get_session()
    try:
        dst = DSTTest(well_id=well_id, test_name=test_name, depth_m=depth_m, **kwargs)
        session.add(dst)
        session.commit()
        return dst
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def save_interpretation(project_id: int, well_id: int, interp_type: str,
                        summary: str = "", ai_narrative: str = "",
                        porosity_summary: dict = None,
                        permeability_summary: dict = None,
                        saturation_summary: dict = None) -> Interpretation:
    """Save an interpretation/summary."""
    session = get_session()
    try:
        interp = Interpretation(
            project_id=project_id,
            well_id=well_id,
            interpretation_type=interp_type,
            summary=summary,
            ai_narrative=ai_narrative,
            porosity_summary=porosity_summary or {},
            permeability_summary=permeability_summary or {},
            saturation_summary=saturation_summary or {},
        )
        session.add(interp)
        session.commit()
        return interp
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def save_ml_model(project_id: int, model_name: str, target_variable: str,
                  input_features: list, mae: float, rmse: float, r2_score: float,
                  training_samples: int, model_bytes: str, notes: str = "") -> MLModel:
    """Save a trained ML model."""
    session = get_session()
    try:
        ml_model = MLModel(
            project_id=project_id,
            model_name=model_name,
            target_variable=target_variable,
            input_features=input_features,
            mae=mae,
            rmse=rmse,
            r2_score=r2_score,
            training_samples=training_samples,
            model_bytes=model_bytes,
            notes=notes,
        )
        session.add(ml_model)
        session.commit()
        return ml_model
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def get_ml_models_for_project(project_id: int) -> list[MLModel]:
    """Get all trained models for a project."""
    session = get_session()
    try:
        return session.query(MLModel).filter_by(project_id=project_id).all()
    finally:
        session.close()