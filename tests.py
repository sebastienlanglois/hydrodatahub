import os
from urllib.request import urlopen
import re
import pandas as pd
import numpy as np
from sqlalchemy.dialects import postgresql


class StationParserCEHQ:
    """

    """

    def __init__(self,
                 url: str = "https://www.cehq.gouv.qc.ca/depot/historique_donnees/fichier/010101_Q.txt",
                 source: str = "MINISTERE DE L'ENVIRONNEMENT DU QUEBEC",
                 encoding: str = "ISO-8859-1",
                 ):

        self.filename: str = url
        self.encoding: str = encoding
        self.content: list = self.open_file(url, encoding)
        self.regularisation: str = self.content[3][15:].split()[-1]
        self.superficie: float = float(self.content[3][15:].split()[0])
        self.numero_station: str = self.content[2].split()[1]
        self.nom_station: str = self.get_station_name()
        self.latitude: float = self.get_lat_long()[0]
        self.longitude: float = self.get_lat_long()[1]
        self.values: pd.Dataframe = self.get_values()
        self.date_debut: str = self.get_start_end_date()[0]
        self.date_fin: str = self.get_start_end_date()[1]
        self.type_serie: str = self.get_type_serie()
        self.pas_de_temps: str = '1_J'
        self.aggregation: str = "moy"
        self.unites: str = "m3/s"
        self.source: str = source
        self.province: str = "QC"

    @staticmethod
    def open_file(filename, encoding) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        with urlopen(filename) as f:
            return f.read().decode(encoding).splitlines()

    def get_station_name(self) -> str:
        """

        :param filename:
        :param encoding:
        :return:
        """
        full_description_line = self.content[2].split('-')[0]
        station_car_index = full_description_line.find(self.numero_station)
        return full_description_line[station_car_index+6:].strip()

    def get_lat_long(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        lat_long = []
        latlng_coordinates = self.content[4][22:-2].split()

        if len(latlng_coordinates) < 5:
            latlng_coordinates = [x for x in latlng_coordinates if x]
            lat_long =  [float(latlng_coordinates[0]), float(latlng_coordinates[2])]
        elif len(latlng_coordinates) >= 5:
            latlng_coordinates = [re.sub(r'[^-\d]', '', coord) for coord in latlng_coordinates]
            latlng_coordinates = [x for x in latlng_coordinates if x]
            lat_long = [float(latlng_coordinates[0]) +
                        float(latlng_coordinates[1]) / 60 +
                        float(latlng_coordinates[2]) / 3600,
                        float(latlng_coordinates[3]) -
                        float(latlng_coordinates[4]) / 60 -
                        float(latlng_coordinates[5]) / 3600]
        return lat_long

    def get_values(self) -> pd.DataFrame:
        """

        :param filename:
        :param encoding:
        :return:
        """
        df = pd.DataFrame(self.content[22:]).fillna(np.nan)[0].str.split(" +", expand=True).iloc[:, 1:3]
        df.columns = ['date', 'value']
        df['value'] = df['value'].apply(pd.to_numeric, errors='coerce')
        df = df.set_index('date')
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize("America/Montreal", ambiguous='infer', nonexistent='shift_forward')
        return df

    def get_start_end_date(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        debut = self.values['value'].dropna().index[0]
        fin = self.values['value'].dropna().index[-1]
        return [debut, fin]

    def get_type_serie(self) -> str:
        """

        :param filename:
        :param encoding:
        :return:
        """
        type_serie_id = self.filename.split('/')[-1].split('.')[0][-1]
        return "Debit" if type_serie_id is "Q" else 'Niveau'


from config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import bassin, meta_series, don_series


class SQLAlchemyDBConnection(object):
    """SQLAlchemy database connection"""

    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.session = None

    def __enter__(self):
        engine = create_engine(self.connection_string)
        Session = sessionmaker()
        self.session = Session(bind=engine)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()


class Bassin():

    def __init__(self,
                 station):
        self.station = station

    @property
    def is_bassin_id_in_db(self) -> bool:
        """

        :return:
        """
        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            if db.session.query(bassin).filter_by(numero_station=self.station.numero_station).first() is not None:
                return True
            else:
                return False

    @property
    def is_time_series_id_in_db(self) -> list:
        """

        :return:
        """
        if self.is_bassin_id_in_db:
            with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
                id_bassin = db.session.query(bassin) \
                                      .filter_by(numero_station=self.station.numero_station) \
                                      .first() \
                                      .id_bassin

                # Get all metadata in database associated with id_bassin unique id and compare with current data point
                meta_time_series_match =[]
                for meta_time_series in db.session.query(meta_series).filter_by(id_bassin=id_bassin).all():
                    df = pd.DataFrame(index=[0],
                                      data={c.name: getattr(meta_time_series, c.name) for
                                            c in meta_time_series.__table__.columns})

                    if self.meta_series[['type_serie', 'pas_de_temps', 'aggregation', 'unites', 'source']] \
                           .equals(df[['type_serie', 'pas_de_temps', 'aggregation', 'unites', 'source']]):
                        meta_time_series_match.append(meta_time_series)

                if any(meta_time_series_match):
                    return [True, meta_time_series_match]
                else:
                    return [False, []]
        else:
            return [False, []]

    def to_sql(self):
        """

        :return:
        """
        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            if not self.is_bassin_id_in_db:
                self.bassin.to_sql(name=bassin.__tablename__,
                                   con=db.session.bind,
                                   if_exists='append',
                                   index=False)

            id_bassin = db.session.query(bassin) \
                .filter_by(numero_station=self.station.numero_station) \
                .first() \
                .id_bassin
            df = self.meta_series
            values = self.don_series
            df.insert(0, 'id_bassin', id_bassin)
            if not self.is_time_series_id_in_db[0]:
                df.to_sql(name=meta_series.__tablename__,
                          con=db.session.bind,
                          if_exists='append',
                          index=False)
                id_ms = self.is_time_series_id_in_db[1][0].id
                values.insert(0, 'id', id_ms)
                values.to_sql(name=don_series.__tablename__,
                              con=db.session.bind,
                              if_exists='append',
                              index=False)
            else:
                id_ms = self.is_time_series_id_in_db[1][0].id
                df.insert(0, 'id', id_ms)
                insrt_stmnt = postgresql.insert(meta_series) \
                                        .values(df.to_dict(orient='records'))
                update_dict = {
                    c.name: c
                    for c in insrt_stmnt.excluded
                    if not c.primary_key
                }
                do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id'],
                                                                    set_=update_dict)
                db.session.bind.execute(do_nothing_stmt)

                id = self.is_time_series_id_in_db[1][0].id
                values.insert(0, 'id', id)
                insrt_stmnt = postgresql.insert(don_series) \
                                        .values(values.to_dict(orient='records'))
                update_dict = {
                    c.name: c
                    for c in insrt_stmnt.excluded
                    if not c.primary_key
                }
                do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id', 'date'],
                                                                    set_=update_dict)
                db.session.bind.execute(do_nothing_stmt)

    @property
    def bassin(self) -> pd.DataFrame:
        """

        :param filename:
        :param encoding:
        :return:
        """

        return pd.DataFrame(index=[0],
                            data={'numero_station': self.station.numero_station,
                                  'nom_station': self.station.nom_station,
                                  'nom_equivalent': "",
                                  'province': self.station.province,
                                  'regularisation': self.station.regularisation,
                                  'superficie': self.station.superficie,
                                  'latitude': self.station.latitude,
                                  'longitude': self.station.longitude})


    @property
    def meta_series(self) -> pd.DataFrame:
        """

        :param filename:
        :param encoding:
        :return:
        """

        return pd.DataFrame(index=[0],
                            data={'type_serie': self.station.type_serie,
                                  'pas_de_temps': self.station.pas_de_temps,
                                  'aggregation': self.station.aggregation,
                                  'unites': self.station.unites,
                                  'date_debut': self.station.date_debut,
                                  'date_fin': self.station.date_fin,
                                  'source': self.station.source})
    @property
    def don_series(self) -> pd.DataFrame:
        """

        :param filename:
        :param encoding:
        :return:
        """

        return self.station.values.drop_duplicates().reset_index()


if __name__ == '__main__':
    station = StationParserCEHQ()
    b = Bassin(station)
    b.to_sql()
    # print(b.is_time_series_id_in_db[0])



