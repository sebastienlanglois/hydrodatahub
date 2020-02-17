from app import db
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine


Base = declarative_base()
engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/hydrodatahub', echo=True)


class region(db.Model):
    __tablename__ = 'region'
    __table_args__ = {'extend_existing': True}
    id_region = db.Column('id_region', db.Integer, primary_key=True)
    nom_region = db.Column('nom_region', db.String)
    value = db.Column('value', db.REAL)

    def __repr__(self):
        return '<date {}>'.format(self.value)


class station(db.Model):
    __tablename__ = 'station'
    __table_args__ = {'extend_existing': True}
    id_station = db.Column('id_station', db.Integer, primary_key=True)
    numero_station = db.Column('numero_station', db.String)
    province = db.Column('province', db.String)
    latitude = db.Column('latitude', db.REAL)
    longitude = db.Column('longitude', db.REAL)
    id_region = db.Column('id_region', db.Integer, db.ForeignKey(region.id_region))

    def __repr__(self):
        return '<amenagement {}>'.format(self.nom_amenagement)


class bassin(db.Model):
    __tablename__ = 'bassin'
    __table_args__ = {'extend_existing': True}
    id_bassin = db.Column('id_bassin', db.Integer, primary_key=True)
    numero_station = db.Column('numero_station', db.String, unique=True)
    nom_station = db.Column('nom_station', db.String)
    nom_equiv = db.Column('nom_equivalent', db.String)
    province = db.Column('province', db.String)
    regime = db.Column('regularisation', db.String)
    superficie = db.Column('superficie', db.Integer)
    latitude = db.Column('latitude', db.REAL)
    longitude = db.Column('longitude', db.REAL)
    id_region = db.Column('id_region', db.Integer, db.ForeignKey(region.id_region))

    def __repr__(self):
        return '<basins {}>'.format(self.id_bassin)


class amenagement(db.Model):
    __tablename__ = 'amenagement'
    __table_args__ = {'extend_existing': True}
    id_amenagement = db.Column('id_amenagement', db.Integer, primary_key=True)
    nom_amenagement = db.Column('nom_amenagement', db.String)
    id_bassin = db.Column('id_bassins', db.Integer, db.ForeignKey(bassin.id_bassin))

    def __repr__(self):
        return '<amenagement {}>'.format(self.nom_amenagement)


class reservoir(db.Model):
    __tablename__ = 'reservoir'
    __table_args__ = {'extend_existing': True}
    id_reservoir = db.Column('id_reservoir', db.Integer, primary_key=True)
    nom_amenagement = db.Column('nom_amenagement', db.String)
    id_bassin = db.Column('id_bassin', db.Integer, db.ForeignKey(bassin.id_bassin))
    id_amenagement = db.Column('id_amenagement', db.Integer, db.ForeignKey(amenagement.id_amenagement))

    def __repr__(self):
        return '<reservoirs {}>'.format(self.id_reservoir)


class evacuateur(db.Model):
    __tablename__ = 'evacuateur'
    __table_args__ = {'extend_existing': True}
    id_evacuateur = db.Column('id_evacuateur', db.Integer, primary_key=True)
    nom_amenagement = db.Column('nom_evacuateur', db.String)
    id_reservoir = db.Column('id_reservoir', db.Integer, db.ForeignKey(reservoir.id_reservoir))
    id_amenagement = db.Column('id_amenagement', db.Integer, db.ForeignKey(amenagement.id_amenagement))

    def __repr__(self):
        return '<evacuateur {}>'.format(self.id_evacuateur)


class centrale(db.Model):
    __tablename__ = 'centrale'
    __table_args__ = {'extend_existing': True}
    id_centrale = db.Column('id_centrale', db.Integer, primary_key=True)
    nom_centrale = db.Column('nom_centrale', db.String)
    id_reservoir = db.Column('id_reservoir', db.Integer, db.ForeignKey(reservoir.id_reservoir))
    id_amenagement = db.Column('id_amenagement', db.Integer, db.ForeignKey(amenagement.id_amenagement))

    def __repr__(self):
        return '<centrale {}>'.format(self.id_centrale)


class meta_series(db.Model):
    __tablename__ = 'meta_series'
    __table_args__ = {'extend_existing': True}
    id = db.Column('id', db.Integer, primary_key=True, unique=True)
    id_bassin = db.Column('id_bassin', db.Integer, db.ForeignKey(bassin.id_bassin))
    type_serie = db.Column('type_serie', db.String)
    pas_de_temps = db.Column('pas_de_temps', db.String)
    aggregation = db.Column('aggregation', db.String)
    unites = db.Column('unites', db.String)
    date_debut = db.Column('date_debut', db.DateTime(timezone=True))
    date_fin = db.Column('date_fin', db.DateTime(timezone=True))
    source = db.Column('source', db.String)

    def __repr__(self):
        return '<meta_ts {}>'.format(self.id)


class don_series(db.Model):
    __tablename__ = 'don_series'
    __table_args__ = {'extend_existing': True}
    id = db.Column('id', db.Integer, db.ForeignKey(meta_series.id), primary_key=True)
    date = db.Column('date', db.DateTime(timezone=True), primary_key=True)
    value = db.Column('value', db.REAL)

    def __repr__(self):
        return '<date {}>'.format(self.value)


Base.metadata.create_all(engine)