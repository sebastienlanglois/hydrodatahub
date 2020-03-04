import pandas as pd
import numpy as np
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from config import Config
import os
from hydrodatahub.database.elements.bassin import Bassin
import geopandas as gpd


class StationParserHYDAT:
    """

    """

    def __init__(self,
                 filename: str,
                 station_number,
                 type_serie: str = 'Debit'
                 ):

        self.filename: str = filename
        self.content: tuple = self.open_file(filename, station_number)
        self.superficie: float = self.content.DRAINAGE_AREA_GROSS
        self.numero_station: str = station_number
        self.nom_station: str = self.content.STATION_NAME
        self.regularisation: str = self.get_regulated()
        self.latitude: float = self.content.LATITUDE
        self.longitude: float = self.content.LONGITUDE
        self.values: pd.Dataframe = self.get_values(type_serie)
        self.date_debut: str = self.get_start_end_date()[0]
        self.date_fin: str = self.get_start_end_date()[1]
        self.type_serie: str = type_serie
        self.nom_equivalent: str = self.get_equivalent_name_and_source()[0]
        self.pas_de_temps: str = '1_J'
        self.aggregation: str = 'moy'
        self.unites: str = self.get_type_serie()[1]
        self.source: str = self.get_equivalent_name_and_source()[1]
        self.province: str = self.content.PROV_TERR_STATE_LOC
        self.geom = self.get_geom()

    @staticmethod
    def open_file(filename, station_number) -> tuple:
        """

        :param station_number:
        :param filename:
        :return:
        """
        with SQLAlchemyDBConnection(filename) as db:
            meta = MetaData(bind=db.session.bind)
            meta.reflect(bind=db.session.bind)

            return db.session.query(meta.tables['STATIONS'], meta.tables['STN_REGULATION']) \
                .filter('STATION_NUMBER' == 'STATION_NUMBER') \
                .filter_by(STATION_NUMBER=station_number) \
                .first()

    def get_geom(self):
        """

        :return:
        """
        url = os.path.join(Config.GEOJSON_BUCKET,
                           'HYDAT/json',
                           self.numero_station,
                           self.numero_station + '.json')
        geom = None

        try:
            gdf = gpd.read_file(url)
            geom = gdf.iloc[0].geometry
        except Exception:
            pass
        return geom

    def get_values(self, type_serie) -> pd.DataFrame:
        """

        :param type_serie:
        :return:
        """

        with SQLAlchemyDBConnection(self.filename) as db:
            meta = MetaData(bind=db.session.bind)
            meta.reflect(bind=db.session.bind)

            if type_serie is "Debit":
                table = 'DLY_FLOWS'
                get_flow = True
            else:
                table = 'DLY_LEVELS'
                get_flow = False

            df = hydat_sqlite_convert(
                pd.DataFrame(
                    db.session.query(meta.tables[table]) \
                        .filter_by(STATION_NUMBER=self.numero_station) \
                        .all()), get_flow, False).drop(columns=['STATION_NUMBER'])

        df.columns = ['date', 'value']
        df['value'] = df['value'].apply(pd.to_numeric, errors='coerce')
        df = df.set_index('date')
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize("America/Montreal", ambiguous='infer', nonexistent='shift_forward')
        df.sort_index(inplace=True)
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

    def get_type_serie(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """

        return ["Debit", "m3/s"] if self.type_serie is "Debit" else ['Niveau', "m"]

    def get_regulated(self) -> str:

        with SQLAlchemyDBConnection(self.filename) as db:
            meta = MetaData(bind=db.session.bind)
            meta.reflect(bind=db.session.bind)

            is_regulated = db.session.query(meta.tables['STN_REGULATION']) \
                .filter_by(STATION_NUMBER=self.numero_station) \
                .first().REGULATED
            print(is_regulated)

        if is_regulated == 0:
            regulated = "Naturel"
        else:
            regulated = "Influence"
        return regulated

    def get_equivalent_name_and_source(self):
        root_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        df = pd.read_csv(os.path.join(root_path, 'offline_data/equivalent_name_stations.csv'))

        equiv_name = df[df['HYDAT'] == self.numero_station]['MDDELCC']
        if not any(equiv_name):
            equiv_name = ""
        else:
            equiv_name = "{:06d}".format(int(equiv_name.values[0]))

        source = df[df['HYDAT'] == self.numero_station]['Source']
        if not any(source):
            source = "WATER SURVEY OF CANADA (DOE) (CANADA)"
        else:
            source = source.values[0]
        if "".__eq__(source):
            source = "WATER SURVEY OF CANADA (DOE) (CANADA)"
        return [equiv_name, source]


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


def hydat_sqlite_convert(df, get_flow, to_plot):
    # Deux ou plus stations
    # station_number = "'02TC001' OR STATION_NUMBER='02TC002'"
    # station1 = "'02TC001'"
    # station2 = "'02TC002'"
    # qstr = "SELECT * FROM DLY_FLOWS WHERE STATION_NUMBER=%s OR STATION_NUMBER=%s\n" %(station1, station2)
    # qstr = SELECT * FROM DLY_FLOWS WHERE STATION_NUMBER='02TC001' OR STATION_NUMBER='02TC002'
    # ATTENTION PEUT ETRE TRES LONG

    # print(df)
    # if get_flow == True:
    #     header = "^FLOW\\d+"
    # else:
    #     header = "^LEVEL\\d+"
    header = "^FLOW\\d+" if get_flow == True else "^LEVEL\\d+"

    dly = df[["STATION_NUMBER", "YEAR", "MONTH"]]
    dly.columns = ["STATION_NUMBER", "YEAR", "MONTH"]

    # value.cols = df.columns[df.filter(regex="^FLOW\\d+")]
    # filter  sur les FLOW
    value = df.filter(regex=header)
    valuecols = value.columns
    # print(dlydata.shape)
    # now melt the offline_data frame for offline_data and flags
    dlydata = pd.melt(df, id_vars=["STATION_NUMBER", "YEAR", "MONTH"], value_vars=valuecols)

    if get_flow is True:
        dlydata["DAY"] = dlydata['variable'].apply(lambda x: np.int8(x[4:]))
    else:
        dlydata["DAY"] = dlydata['variable'].apply(lambda x: np.int8(x[5:]))
    # flowvariable = dlydata["variable"]
    # days = [x[4:6] for x in flowvariable]
    # dlydata["DAY"] = list(map(int, days))
    # censor ambiguous dates (e.g., 31st day for Apr, Jun, Sept, Nov)
    d = dlydata.loc[dlydata["MONTH"].isin([4, 6, 9, 11]) & (dlydata["DAY"] > 30)]
    d30 = d
    # print(d.index[:])
    # print(len(d))#

    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    # print(dlydata.shape)

    d = dlydata.loc[(dlydata["MONTH"].isin([2]) &
                     pd.to_datetime(dlydata["YEAR"], format='%Y').dt.is_leap_year &
                     (dlydata["DAY"] > 29))]
    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    d29 = d
    # print(dlydata.shape)

    d = dlydata.loc[(dlydata["MONTH"].isin([2]) &
                     ~pd.to_datetime(dlydata["YEAR"], format='%Y').dt.is_leap_year.values &
                     (dlydata["DAY"] > 28))]
    # print(d)
    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    d28 = d
    # print(dlydata.shape)
    # print(valuecols)

    # ----------------------------------SYMBOL--------------------------------------------------
    header_sym = "^FLOW_SYMBOL\\d+" if get_flow == True else "^LEVEL_SYMBOL\\d+"
    flag = df.filter(regex=header_sym)
    flagcols = flag.columns
    # print(flagcols)
    # ordonner les flag dans un dataframe
    dlyflags = pd.melt(df, id_vars=["STATION_NUMBER", "YEAR", "MONTH"], value_vars=flagcols)

    if len(d30) > 0:
        dlyflags = dlyflags.drop(d30.index).reset_index(drop=True)
    # print(dlyflags.shape)

    if len(d29) > 0:
        dlyflags = dlyflags.drop(d29.index).reset_index(drop=True)
    # print(dlyflags.shape)

    if len(d28) > 0:
        dlyflags = dlyflags.drop(d28.index).reset_index(drop=True)
    # print(dlyflags.shape)
    # -----------------------------------END SYMBOL---------------------------------------------

    # transform date
    dlydata.insert(loc=1, column='DATE', value=pd.to_datetime(dlydata[['YEAR', 'MONTH', 'DAY']]))
    # ---------------------------------plot the dataframe--------------------------------------
    dlytoplot = dlydata[['DATE', 'value']].set_index('DATE')
    dlydata = dlydata.drop(['YEAR', 'MONTH', 'DAY', 'variable'], axis=1)

    if to_plot == 1:
        dlytoplot.plot()
        return dlytoplot
    else:
        return dlydata


def get_available_stations_from_hydat(regions_list=['QC', 'ON', 'NB', 'NL']):
    """
    Get list of all available stations from cehq with station's number and name as value
    """
    hydat_sqlite = 'sqlite:///' + \
                   os.path.join(Config.SQLITE_HYDAT_FOLDER,
                                "Hydat.sqlite3")

    with SQLAlchemyDBConnection(hydat_sqlite) as db:
        df = pd.read_sql_query("SELECT * FROM STATIONS", db.session.bind)
    return df[df['PROV_TERR_STATE_LOC'].isin(regions_list)]['STATION_NUMBER']


from hydrodatahub.models import bassin


def is_id_bassin_in_db(station):
    with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
        if db.session.query(bassin).filter_by(nom_equiv=station).first() is not None:
            return True
        else:
            return False


def import_hydat_to_sql(station):
    """

    :param station:
    :return:
    """
    hydat_sqlite = 'sqlite:///' + \
                   os.path.join(Config.SQLITE_HYDAT_FOLDER,
                                "Hydat.sqlite3")
    print(station.strip())

    if not is_id_bassin_in_db(station):

        try:
            sta = StationParserHYDAT(filename=hydat_sqlite,
                                     station_number=station.strip(),
                                     type_serie='Debit')
            b = Bassin(sta)
            b.to_sql()
        except Exception:
            pass
        # try:
        #     sta = StationParserHYDAT(filename=hydat_sqlite,
        #                              station_number=station.strip(),
        #                              type_serie='Niveau')
        #     b = Bassin(sta)
        #     b.to_sql()
        # except Exception:
        #     pass

# if __name__ == '__main__':
#     # list_of_hydat_sqlite = glob.glob(os.path.join(Config.SQLITE_HYDAT_FOLDER, '*.zip'),
#     #                                  recursive=True)
#     #
#     # latest_file = max(list_of_hydat_sqlite, key=os.path.getctime)
#     # import zipfile
#     #
#     # with zipfile.ZipFile(latest_file, 'r') as zip_ref:
#     #     zip_ref.extractall(Config.SQLITE_HYDAT_FOLDER)
#     hydat_sqlite = 'sqlite:///' + \
#                    os.path.join(Config.SQLITE_HYDAT_FOLDER,
#                                 "Hydat.sqlite3")
#     df = get_available_stations_from_hydat(hydat_sqlite)
#     print(df.columns)
#     station = StationParserHYDAT(filename=hydat_sqlite,
#                                  type_serie='Debit')
#     print(station.content)
#     print(station.nom_equivalent)
#     print(station.get_values())
#
#     # all_dfs = parse_data_from_hydat_files('/home/slanglois/Downloads/Hydat_sqlite3_20191016/Hydat.sqlite3',
#     #                                   regions_list=['QC', 'ON', 'NB', 'NL'])
#     # df_to_sql(all_dfs)
#     # #delete_files_in_store()
