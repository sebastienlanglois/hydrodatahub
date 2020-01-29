from app import db

# Base = declarative_base()
# engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/hydrodatahub', echo=True)
#


class basins(db.Model):
    id_point = db.Column('id_point', db.Integer, primary_key=True)
    numero_station = db.Column('station_number', db.String)
    nom_station = db.Column('station_name', db.String)
    nom_equiv = db.Column('equivalent_name', db.String)
    province = db.Column('province', db.String)
    regime = db.Column('regulation', db.String)
    superficie = db.Column('drainage_area', db.Integer)
    latitude = db.Column('latitude', db.REAL)
    longitude = db.Column('longitude', db.REAL)

    def __repr__(self):
        return '<basins {}>'.format(self.id_point)


class meta_ts(db.Model):
    id_serie = db.Column('id_time_serie', db.Integer, primary_key=True)
    id_point = db.Column('id_point', db.Integer, db.ForeignKey(basins.id_point))
    type_serie = db.Column('data_type', db.String)
    pas_de_temps = db.Column('time_step', db.String)
    aggregation = db.Column('aggregation', db.String)
    unite = db.Column('units', db.String)
    date_debut = db.Column('start_date', db.DateTime(timezone=True))
    date_fin = db.Column('end_date', db.DateTime(timezone=True))
    source = db.Column('source', db.String)

    def __repr__(self):
        return '<meta_ts {}>'.format(self.id_serie)


class don_ts(db.Model):
    id_serie = db.Column('id_time_serie', db.Integer, db.ForeignKey(meta_ts.id_serie), primary_key=True)
    date = db.Column('date', db.DateTime(timezone=True), primary_key=True)
    value = db.Column('value', db.REAL)

    def __repr__(self):
        return '<date {}>'.format(self.value)

# Base.metadata.create_all(engine)