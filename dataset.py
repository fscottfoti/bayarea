import numpy as np
import pandas as pd
import os
from urbansim.utils import misc, dataset
from urbansim.utils.dataset import variable

import warnings
warnings.filterwarnings('ignore', category=pd.io.pytables.PerformanceWarning)


class BayAreaDataset(dataset.Dataset):

    def __init__(self, filename):
        self.scenario = "baseline"
        super(BayAreaDataset, self).__init__(filename)

    def add_zone_id(self, df):
        return self.join_for_field(df, 'buildings', 'building_id', 'zone_id')

    def fetch_jobs(self):
        return self.nets

    @staticmethod
    def fetch_nodes():
        # default will fetch off disk unless networks have already been run
        print "WARNING: fetching precomputed nodes off of disk"
        df = pd.read_csv(os.path.join(misc.data_dir(), 'nodes.csv'), index_col='node_id')
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
        return df

    @staticmethod
    def fetch_nodes_prices():
        # default will fetch off disk unless networks have already been run
        print "WARNING: fetching precomputed nodes_prices off of disk"
        df = pd.read_csv(os.path.join(misc.data_dir(), 'nodes_prices.csv'), index_col='node_id')
        df = df.replace([np.inf, -np.inf], np.nan).fillna(0)
        return df

    @staticmethod
    def fetch_building_sqft_per_job():
        return pd.read_csv(os.path.join(misc.data_dir(), 'building_sqft_job.csv'),
                           index_col='building_type_id')

    def fetch_jobs(self):
        nets = self.store['nets']
        # go from establishments to jobs
        jobs = nets.loc[np.repeat(nets.index.values, nets.emp11.values)].reset_index()
        jobs.index.name = 'job_id'
        return jobs

    def fetch_households(self):
        households = self.store['households']
        households["building_id"][households.building_id == -1] = np.nan
        return households

    def fetch_costar(self):
        costar = self.store['costar']
        return costar[costar.PropertyType.isin(["Office", "Retail", "Industrial", "Flex"])]

    def fetch_zoning_for_parcels(self):
        df = self.store['zoning_for_parcels']
        return df.reset_index().drop_duplicates(cols='parcel').set_index('parcel')

    def fetch_zoning_baseline(self):
        assert self.zoning_for_parcels.index.is_unique
        return pd.merge(self.zoning_for_parcels, self.zoning, left_on='zoning', right_index=True)

    @staticmethod
    def fetch_zoning_test():
        parcels_to_zoning = pd.read_csv(os.path.join(misc.data_dir(), 'parcels_to_zoning.csv'))
        scenario_zoning = pd.read_excel(os.path.join(misc.data_dir(), 'zoning_scenario_test.xls'),
                                        sheetname='zoning_lookup')
        df = pd.merge(parcels_to_zoning, scenario_zoning,
                      on=['jurisdiction', 'pda', 'tpp', 'expansion'], how='left')
        df = df.set_index(df.parcel_id)
        return df

    def set_scenario(self, scenario):
        assert scenario in ["baseline", "test"]
        self.scenario = scenario

    def merge_nodes(self, df):
        return pd.merge(df, self.nodes, left_on="_node_id", right_index=True)

    def clear_views(self):
        self.views = {
            "nodes": self.nodes,
            "parcels": Parcels(self),
            "households": Households(self),
            "homesales": HomeSales(self),
            "jobs": Jobs(self),
            "costar": CoStar(self),
            "apartments": Apartments(self),
            "buildings": Buildings(self),
        }


class Buildings(dataset.CustomDataFrame):

    BUILDING_TYPE_MAP = {
        1: "Residential",
        2: "Residential",
        3: "Residential",
        4: "Office",
        5: "Hotel",
        6: "School",
        7: "Industrial",
        8: "Industrial",
        9: "Industrial",
        10: "Retail",
        11: "Retail",
        12: "Residential",
        13: "Retail",
        14: "Office"
    }

    def __init__(self, dset):
        super(Buildings, self).__init__(dset, "buildings")
        self.flds = ["year_built", "unit_lot_size", "unit_sqft", "_node_id", "general_type",
                     "stories", "residential_units", "non_residential_units", "building_type_id",
                     'x', 'y']

    @property
    def general_type(self):
        return self.building_type_id.map(self.BUILDING_TYPE_MAP)

    @variable
    def unit_sqft(self):
        return "buildings.building_sqft / buildings.residential_units"

    @variable
    def unit_lot_size(self):
        return "buildings.lot_size / buildings.residential_units"

    @property
    def non_residential_units(self):
        sqft_per_job = misc.reindex(self.dset.building_sqft_per_job.sqft_per_job,
                                    self.building_type_id.fillna(-1))
        return (self.non_residential_sqft/sqft_per_job).fillna(0).astype('int')


class CoStar(dataset.CustomDataFrame):

    def __init__(self, dset):
        super(CoStar, self).__init__(dset, "costar")
        self.flds = ["rent", "stories", "_node_id", "year_built"]

    @property
    def rent(self):
        return self.df.averageweightedrent

    @property
    def stories(self):
        return self.df.number_of_stories


class Apartments(dataset.CustomDataFrame):

    def __init__(self, dset):
        super(Apartments, self).__init__(dset, "apartments")
        self.flds = ["_node_id", "rent", "unit_sqft"]

    @variable
    def _node_id(self):
        return "reindex(parcels._node_id, apartments.parcel_id)"

    @property
    def rent(self):
        return (self.df.MinOfLowRent+self.df.MaxOfHighRent)/2.0/self.unit_sqft

    @property
    def unit_sqft(self):
        return self.df.AvgOfSquareFeet


class Households(dataset.CustomDataFrame):

    def __init__(self, dset):
        super(Households, self).__init__(dset, "households")
        self.flds = ["income", "income_quartile", "building_id", "tenure", "persons", "x", "y"]

    @property
    def income_quartile(self):
        return pd.Series(pd.qcut(self.df.income, 4).labels, index=self.df.index)

    @variable
    def x(self):
        return "reindex(buildings.x, households.building_id)"

    @variable
    def y(self):
        return "reindex(buildings.y, households.building_id)"


class Jobs(dataset.CustomDataFrame):

    def __init__(self, dset):
        super(Jobs, self).__init__(dset, "jobs")
        self.flds = ["building_id", "x", "y"]

    @variable
    def x(self):
        return "reindex(buildings.x, jobs.building_id)"

    @variable
    def y(self):
        return "reindex(buildings.y, jobs.building_id)"


class HomeSales(dataset.CustomDataFrame):

    def __init__(self, dset):
        super(HomeSales, self).__init__(dset, "homesales")
        self.flds = ["sale_price_flt", "year_built", "unit_lot_size", "unit_sqft", "_node_id"]

    @property
    def sale_price_flt(self):
        return self.df.Sale_price.str.replace('$', '').str.replace(',', '').astype('f4') / \
            self.unit_sqft

    @property
    def year_built(self):
        return self.df.Year_built

    @property
    def unit_lot_size(self):
        return self.df.Lot_size

    @property
    def unit_sqft(self):
        return self.df.SQft


class Parcels(dataset.CustomDataFrame):

    type_d = {
        'residential': [1, 2, 3],
        'industrial': [7, 8, 9],
        'retail': [10, 11],
        'office': [4],
        'mixedresidential': [12],
        'mixedoffice': [14],
    }

    def __init__(self, dset):
        super(Parcels, self).__init__(dset, "parcels")
        self.flds = ["parcel_size", "total_units", "total_sqft", "land_cost", "max_far",
                     "max_height"]

    def price(self, use):
        return misc.reindex(self.dset.nodes_prices[use], self.df._node_id)

    def allowed(self, form):
        # we have zoning by building type but want to know if specific forms are allowed
        allowed = [self.dset.zoning_baseline['type%d' % typ] == 't' for typ in self.type_d[form]]
        return pd.concat(allowed, axis=1).max(axis=1).reindex(self.df.index).fillna(False)

    @property
    def max_far(self):
        baseline = self.dset.zoning_baseline
        max_far = baseline.max_far
        if self.dset.scenario == "test":
            upzone = self.dset.zoning_test_scenario.far_up.dropna()
            max_far = pd.concat([max_far, upzone], axis=1).max(skipna=True, axis=1)
        return max_far.reindex(self.df.index).fillna(0)

    @property
    def max_height(self):
        return self.dset.zoning_baseline.max_height\
            .reindex(self.df.index).fillna(0)

    @variable
    def parcel_size(self):
        return "parcels.shape_area * 10.764"

    @variable
    def ave_unit_sqft(self):
        return "reindex(nodes.ave_unit_sqft, parcels._node_id)"

    @variable
    def total_units(self):
        return "buildings.groupby(buildings.parcel_id).residential_units.sum().fillna(0)"

    @variable
    def total_sqft(self):
        return "buildings.groupby(buildings.parcel_id).building_sqft.sum().fillna(0)"

    @property
    def land_cost(self):
        # TODO
        # this needs to account for cost for the type of building it is
        return (self.total_sqft * self.price("residential"))\
            .reindex(self.df.index).fillna(0)


LocalDataset = BayAreaDataset