import pandas as pd
from config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import postgresql
from hydrodatahub.models import bassin, meta_series, don_series
import geopandas as gpd
from geoalchemy2 import Geometry, WKTElement
from binascii import hexlify
import uuid
import json
from shapely.geometry import Polygon, mapping


class Bassin:
    """

    """

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
                uid = db.session.query(bassin) \
                    .filter_by(numero_station=self.station.numero_station) \
                    .first() \
                    .uid

                # Get all metadata in database associated with id_bassin unique id and
                # compare with current offline_data point
                meta_time_series_match = []
                for meta_time_series in db.session.query(meta_series).filter_by(uid=uid).all():
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
                connection = db.session.bind.raw_connection()
                cursor = connection.cursor()
                insert_query = """SELECT md5(random()::text || clock_timestamp()::text)::uuid"""
                cursor.execute(insert_query)
                uid = cursor.fetchone()[0]
                df_bassin = self.bassin
                df_bassin.insert(0, 'uid', uid)
                df_bassin.to_sql(name=bassin.__tablename__,
                                 con=db.session.bind,
                                 if_exists='append',
                                 index=False)

                poly = self.station.geom
                if poly is not None:
                    geom = mapping(poly)
                    geom = json.dumps(geom)
                    geom = geom.replace('(', '[')
                    geom = geom.replace(')', ']')

                    insert_query = """UPDATE public.bassin SET geometry = ST_SetSRID(ST_GeomFromGeoJSON('{geom}'), 4326)
                    WHERE numero_station in ('{numero_station}')""".format(geom=geom,
                                                                           numero_station=self.station.numero_station)
                    cursor.execute(insert_query)
                    connection.commit()

                insert_query = """UPDATE public.bassin SET latlon = 
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326);"""
                cursor.execute(insert_query)
                connection.commit()

                # id_bassin = db.session.query(bassin) \
                #     .filter_by(numero_station=self.station.numero_station) \
                #     .first() \
                #     .id_bassin
                #
                #
                #
                # id_object_df.to_sql(name=elements.__tablename__,
                #                     con=db.session.bind,
                #                     if_exists='append',
                #                     index=False)

            # id_bassin = db.session.query(bassin) \
            #     .filter_by(numero_station=self.station.numero_station) \
            #     .first() \
            #     .id_bassin

            uid = db.session.query(bassin) \
                .filter_by(numero_station=self.station.numero_station) \
                .first() \
                .uid

            df = self.meta_series
            values = self.don_series

            df.insert(0, 'uid', uid)
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
        # crs = {'init': 'epsg:4326'}
        # return gpd.GeoDataFrame(pd.DataFrame(index=[0],
        #                                      data={'numero_station': self.station.numero_station,
        #                                            'nom_station': self.station.nom_station,
        #                                            'nom_equivalent': self.station.nom_equivalent,
        #                                            'province': self.station.province,
        #                                            'regularisation': self.station.regularisation,
        #                                            'superficie': self.station.superficie,
        #                                            'latitude': self.station.latitude,
        #                                            'longitude': self.station.longitude}),
        #                         crs=crs,
        #                         geometry=[self.station.geom])
        return pd.DataFrame(index=[0],
                            data={'numero_station': self.station.numero_station,
                                  'nom_station': self.station.nom_station,
                                  'nom_equivalent': self.station.nom_equivalent,
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
        df = self.station.values
        df = df.loc[~df.index.duplicated(keep='first')]
        mask = (df.index >= self.station.date_debut) & (df.index <= self.station.date_fin)
        return df.loc[mask].reset_index()


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
