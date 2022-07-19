import os
import numpy as np
from typing import Union
from obspy.core.event.catalog import Catalog, read_events
from obspy.geodetics.base import gps2dist_azimuth

from . import utils as ut
from SeisMonitor import utils as sut
from SeisMonitor.monitor.locator import utils as slut

class NLLoc():
    def __init__(self,
                region:list,
                nodes:list,
                basic_inputs:slut.LocatorBasicInputs,
                kwargs_for_trans:dict={},
                kwargs_for_vel2grid:dict={},
                kwargs_for_grid2time:dict={},
                kwargs_for_time2loc:dict={}):

        self.region = region
        self.nodes = nodes
        self.basic_inputs = basic_inputs
        self.kwargs_for_trans = kwargs_for_trans
        self.kwargs_for_vel2grid = kwargs_for_vel2grid
        self.kwargs_for_grid2time = kwargs_for_grid2time
        self.kwargs_for_time2loc = kwargs_for_time2loc

    def _prepare_grid_args(self):
        lonw,lone,lats,latn,zmin,zmax = self.region
        lat_center = abs(latn-lats)/2 + lats
        lon_center = abs(lonw-lone)/2 + lonw

        d,az,baz = gps2dist_azimuth(lats,lonw,lat_center,lon_center)
        d = d/1e3
        
        x = d* np.sin(az*np.pi/180)
        y = d* np.cos(az*np.pi/180)

        lon_node_dist,_,_ = gps2dist_azimuth(lats,lonw,lats,lone)
        lon_node_dist = lon_node_dist/1e3/self.nodes[0]
        lat_node_dist,_,_ = gps2dist_azimuth(lats,lonw,latn,lonw)
        lat_node_dist = lat_node_dist/1e3/self.nodes[1]
        z_node_dist = abs(zmax-zmin)/self.nodes[2]

        args = {"trans":["SIMPLE",lat_center,lon_center,0],
                "velgrid":[2,self.nodes[1],self.nodes[2],
                            round(-x,1),round(-y,1),-5.0,
                            3.0,3.0,
                            3.0,"SLOW_LEN"],
                "locgrid":[self.nodes[0],self.nodes[1],self.nodes[2],
                            round(-x,1),round(-y,1),-5.0,
                            3.0,3.0,
                            3.0,
                            "PROB_DENSITY","SAVE"]
                            }
        return args

    def _prepare_basic_inputs(self,tmp_folder:str = os.getcwd()):
        vel_model_out = os.path.join(tmp_folder,"vel_model.dat")
        station_out = os.path.join(tmp_folder,"station.dat")
        catalog_out = os.path.join(tmp_folder,"catalog.out")
        
        sut.isfile(vel_model_out)
        self.basic_inputs.vel_model.to_nlloc(vel_model_out)
        sut.isfile(station_out)
        self.basic_inputs.stations.to_nlloc(station_out)
        sut.isfile(catalog_out)
        self.basic_inputs.catalog.write(catalog_out,
                                        format="NORDIC")
        return vel_model_out,station_out,catalog_out


    def _write_control_files(self,tmp_folder:str=os.getcwd()):

        p_control_file_out = os.path.join(tmp_folder,"p_nlloc.in")
        s_control_file_out = os.path.join(tmp_folder,"s_nlloc.in")
        grid_folder_out = os.path.join(tmp_folder,"model","layer")
        time_folder_out = os.path.join(tmp_folder,"time","layer")
        loc_folder_out = os.path.join(tmp_folder,"loc","SeisMonitor")
        vel_model_path,station_path,catalog_path = self._prepare_basic_inputs(tmp_folder)
        
        grid_args = self._prepare_grid_args()

        if "trans" in list(self.kwargs_for_trans.keys()):
            grid_args["trans"] = self.kwargs_for_trans["trans"]
        if "grid" in list(self.kwargs_for_vel2grid.keys()):
            grid_args["velgrid"] = self.kwargs_for_vel2grid["grid"]
        if "grid" in list(self.kwargs_for_grid2time.keys()):
            grid_args["locgrid"] = self.kwargs_for_grid2time["grid"]


        gen_control = ut.GenericControlStatement(trans=grid_args["trans"])
        vel2grid = ut.Vel2Grid(vel_path=vel_model_path,
                    grid_folder_out=grid_folder_out,
                    grid=grid_args["velgrid"])
        p_grid2time = ut.Grid2Time(station_path=station_path,
                            grid_folder_out=grid_folder_out,
                            time_folder_out=time_folder_out,
                            phase="P")
        s_grid2time = ut.Grid2Time(station_path=station_path,
                            grid_folder_out=grid_folder_out,
                            time_folder_out=time_folder_out,
                            phase="S")

        time2loc = ut.Time2Loc(catalog=[catalog_path,"SEISAN"],
                    grid = grid_args["locgrid"],
                    time_folder_out=time_folder_out,
                    loc_folder_out=loc_folder_out)

        p_nlloc = ut.NLLocControlFile(gen_control,vel2grid,
                                    p_grid2time,time2loc)
        p_nlloc.write(p_control_file_out)
        s_nlloc = ut.NLLocControlFile(gen_control,vel2grid,
                        s_grid2time,time2loc)
        s_nlloc.write(s_control_file_out)

        return p_control_file_out,s_control_file_out

    def relocate(self,
                out:str = None,
                out_format:str = "NORDIC",
                tmp_folder:str = os.getcwd(),
                rm_tmp_folder:bool = False):
        
        p_control_file_path,s_control_file_path = self._write_control_files(tmp_folder)
        ut.run_nlloc(p_control_file_path,
                        s_control_file_path)
        