import logging
from copy import copy
from datetime import date
from pathlib import Path
from typing import List, NoReturn

import pandas as pd

from iea_scraper.core.job import ExtDbApiJob
from iea_scraper.core.source import BaseSource
from iea_scraper.settings import FILE_STORE_PATH

logger = logging.getLogger(__name__)

PROVIDER = 'TH_GO_EPPO'
BASE_URL = "http://www.eppo.go.th/index.php/en/en-energystatistics/petroleum-statistic"
FREQUENCY = "Monthly"
JOB_CODE = Path(__file__).parent.parts[-1]
AREA = "THAILAND"
FLOW = "SUPPLY"
PRODUCT = "CRUDEOIL"
UNIT = 'KBD'
FILE = 'th_go_eppo_T02_01_01.xls'

URL = 'http://www.eppo.go.th/epposite/images/Energy-Statistics/' \
      'energyinformation/Energy_Statistics/Petroleum/T02_01_01.xls'


class ThOilSupplyJob(ExtDbApiJob):
    """
    This scraper will extract monthly crude oil production data by field
    from the thailand Ministry of Energy webpage
    """
    title: str = "Thailand - Production of Crude Oil by field"

    def get_sources(self):
        """
        Implements method get_sources from parent class.
        It defines all data sources that have to be processed.
        Should create a list of object BaseSource in self.sources with at least
        3 attributes: 'url', 'code', 'path'
        :return:None
        """

        source = BaseSource(url=URL,
                            code=FILE.split(".")[0].upper(),
                            path=FILE,
                            long_name=f"{AREA}"
                                      f" Monthly Crude Oil Production by field")

        self.sources.append(source)

        # add dictionary to dynamic dims
        for source in self.sources:
            dicto = vars(copy(source))
            self.dynamic_dim['source'] += [dicto]

        self.remove_existing_dynamic_dim('source')

    def __transform_provider(self):
        """
        Loads the provider dimension.
        :return: None
        """
        logger.debug("Transforming provider ...")
        provider = dict()
        provider["code"] = PROVIDER
        provider["long_name"] = "THAILAND Energy Policy and Planning Office"
        provider["url"] = "http://www.eppo.go.th/index.php/en/en-energystatistics/petroleum-statistic"

        logger.debug(f"Adding provider to dynamic_dim: {PROVIDER}")
        self.dynamic_dim['provider'] = [provider]
        self.remove_existing_dynamic_dim('provider')

    @staticmethod
    def  __get_data_from_source(file: Path) -> pd.DataFrame:
        """
        Transform each downloaded source file.
        :param file: a BaseSource instance detailing the source file.
        :return: data frame containing the source rows
        """

        logger.info(f"Opening {file}")
        # read the excel sheet and convert it to data frame
        df = pd.read_excel(file, header=[0], skiprows=4)
        logger.debug(f"{len(df)} rows read from file {file}")
        df = df.rename(columns={"Date": "period"})
        logger.debug('Renaming the Date column into Period column.')
        return df

    @staticmethod
    def __split_df(df: pd.DataFrame) -> pd.DataFrame:
        """
        a function to split and parse data frame.
        It returns a data frame containing CRUDEOIL production by fields.
        :param df: data frame containing the whole data from excel sheet.
        :return: df with CRUEDOIL production info by fields.
        """
        logger.debug('Collecting indices corresponding to NAN values on first column')
        break_index = df.loc[df.iloc[:, 0].isna()].index
        table_list_1 = []
        start_index = 1
        end_index = 1
        for index in break_index:
            logger.debug(f'beginning of the loop: {index}, {start_index}, {end_index}')
            if start_index == index:
                start_index = index + 1
                logger.debug('continue!')
                continue
            logger.debug('define end_index...')
            end_index = (index - 1)
            table_list_1.append(df.loc[start_index:end_index].copy())
            logger.debug(start_index, end_index)
            start_index = index + 1
        logger.debug(f'Dataframe split in {len(table_list_1)}.')
        logger.debug('Splitting the dataframe on spaces on first column and keeping the '
                     'part corresponding to the second index ')
        df = table_list_1[1]
        return df

    @staticmethod
    def __split_df_further(df: pd.DataFrame) -> List[pd.DataFrame]:
        """
        A function to split the dataframe returned by the method __split_df into 3 dataframes.
        It returns a list of dataframe containing CRUDEOIL production by fields that will later be
        split into 3 dataframes with respect to the different periods.
        :param df: the dataframe returned by the method __split_df used above.
        :return: a list of dataframes that will later be sub-divided into thee dataframes df_1, df_2, df_3.
        """
        logger.debug('Splitting data frame on rows containing the keyword YTD on first column')
        break_index = df.loc[df.iloc[:, 0].str.contains('YTD')].index
        table_list_2 = []
        start_index = 1
        end_index = 1
        for index in break_index:
            logger.debug(f'begin of loop: {index}, {start_index}, {end_index}')
            if start_index == index:
                start_index = index + 1
                logger.debug('continue!')
                continue
            logger.debug('define end_index...')
            end_index = (index - 1)
            table_list_2.append(df.loc[start_index:end_index].copy())
            logger.debug(start_index, end_index)
            start_index = index + 1
        logger.debug(f'Dataframe split in {len(table_list_2)}.')

        return table_list_2

    def __filter_and_concat_monthly_data(self, table_list: List[pd.DataFrame]) -> pd.DataFrame:
        """
        This method filters monthly data, formats the period and concatenate it into one dataframe.
        :param table_list: the list of dataframes returned by the method __split_df.
        :return: a concatenated dataframe.
        """
        dfs = [self._map_period(df) for df in table_list]
        return pd.concat(dfs)

    @staticmethod
    def _map_period(df: pd.DataFrame) -> pd.DataFrame:
        """
        The year is the first column of the first row. Concat it to period.
        Raise ValueError if year not numeric.
        :param df: the dataframe to transform.
        :return: a list of all monthly values
        """
        year = df.iloc[0, 0]
        df = df.iloc[1:, :]
        if not year.isnumeric():
            raise ValueError(f'Year read from excel file is not numeric: {year}')
        logger.debug(f'Processing {year}')

        df.loc[:, 'period'] = df.loc[:, 'period'].str.strip().str.upper() + year
        return df

    def transform(self):
        """
         This function reads data from each data source in self.sources and transforms it into a dataframe
        :return:  a Pandas DataFrame.
        """
        logger.info("Transforming data...")
        self.__transform_provider()
        self.data = []

        for source in self.sources:
            logger.debug(f'processing {source.path}')
            file_path = FILE_STORE_PATH / source.path

            df = self.__get_data_from_source(file_path)
            df = self.__split_df(df)
            df = self.__filter_and_concat_monthly_data(self.__split_df_further(df))

            # remove column Total
            del df['Total']

            # melt fields
            df = pd.melt(df, id_vars=['period'], var_name='entity')
            
            # remove null values
            df.dropna(subset=['value'], inplace=True)
            logger.debug(f'Number of rows after removing nulls: {len(df)}')

            # process entities
            self.__transform_entity(df)

            df['value'] = df['value'] / 1000
            df.loc[:, 'entity'] = f'{AREA}_' + df.loc[:, 'entity'].str.upper()

            df = (df.assign(provider=PROVIDER,
                            source=source.code,
                            area=AREA,
                            frequency=FREQUENCY,
                            flow=FLOW,
                            product=PRODUCT,
                            unit=UNIT,
                            original=True))
            # Loading the results into self.data
            self.data.extend(df.to_dict('records'))
            logger.debug("data transformation complete.")

    def __transform_entity(self, df: pd.DataFrame) -> NoReturn:
        """
        List distinct fields to send to entity dimension.
        :param df: the final df containing entities.
        :return: NoReturn
        """
        logger.debug('Processing entities')
        df_entity = df[['entity']].drop_duplicates()

        logger.debug(f'Number of entities: {len(df_entity)}')

        df_entity['code'] = f'{AREA}_' + df_entity['entity'].str.upper()
        df_entity['long_name'] = f'{AREA} ' + df_entity['entity'].str.title()
        df_entity['category'] = 'field'

        del df_entity['entity']

        # add dictionary to dynamic dims
        self.dynamic_dim['entity'] = df_entity.to_dict('records')
        self.remove_existing_dynamic_dim('entity')
