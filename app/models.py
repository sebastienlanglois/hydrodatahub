from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, REAL
from sqlalchemy import create_engine
from app import db
import psycopg2

# Base = declarative_base()
# engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/hydrodatahub', echo=True)
#

class Bassins(db.Model):
    __tablename__ = 'basins'
    id_point = Column('id_point', Integer, primary_key=True)
    numero_station = Column('station_number', String)
    nom_station = Column('station_name', String)
    nom_equiv = Column('equivalent_name', String)
    province = Column('province', String)
    regime = Column('regulation', String)
    superficie = Column('drainage_area', Integer)
    latitude = Column('latitude', REAL)
    longitude = Column('longitude', REAL)


class Meta_ts(db.Model):
    __tablename__ = 'meta_ts'
    id_serie = Column('id_time_serie', Integer, primary_key=True)
    id_point = Column('id_point', Integer, ForeignKey(Bassins.id_point))
    type_serie = Column('data_type', String)
    pas_de_temps = Column('time_step', String)
    aggregation = Column('aggregation', String)
    unite = Column('units', String)
    date_debut = Column('start_date', DateTime(timezone=True))
    date_fin = Column('end_date', DateTime(timezone=True))
    source = Column('source', String)


class Don_ts(db.Model):
    __tablename__ = 'don_ts'
    id_serie = Column('id_time_serie', Integer, ForeignKey(Meta_ts.id_serie), primary_key=True)
    date = Column('date', DateTime(timezone=True), primary_key=True)
    value = Column('value', REAL)


# Base.metadata.create_all(engine)