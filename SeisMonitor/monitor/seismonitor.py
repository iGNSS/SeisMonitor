import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import os
import glob
import shutil
from SeisMonitor.monitor.downloader.utils import get_chunktimes
from SeisMonitor.monitor.downloader.seismonitor import MseedDownloader
from SeisMonitor.monitor.downloader.utils import sanitize_provider_times
from SeisMonitor.monitor.picker import ai as ai_picker
from SeisMonitor.monitor.associator import ai as ai_asso
from SeisMonitor.monitor.locator.nlloc import nlloc

def get_preproc_providers(providers,chunklength_in_sec,
                            out_folder):
    sanitize_provider_times(providers)
    oneprovider = providers[0]
    restrictions = oneprovider.waveform_restrictions
    starttime = restrictions.starttime
    endtime = restrictions.endtime
    chunktimes = get_chunktimes(starttime,endtime,
                                chunklength_in_sec)
    preproc_providers = []
    for starttime,endtime in chunktimes:
        folders = get_folders_by_chunk(out_folder,
                                        starttime,endtime)

        new_providers = []
        for provider in providers:
            provider = provider.copy()
            provider.waveform_restrictions.starttime = starttime
            provider.waveform_restrictions.endtime = endtime
            new_providers.append(provider)

        chunk_provider = {"providers":new_providers,
                        "folders":folders}
        preproc_providers.append(chunk_provider)
    return preproc_providers



def get_chunktimes_by_provider(providers,chunklength_in_sec):
    times_by_provider = {}
    for provider in providers:
        restrictions = provider.waverform_restrictions
        starttime = restrictions.starttime
        endtime = restrictions.endtime

        times = get_chunktimes(starttime,endtime,
                                chunklength_in_sec)
        times_by_provider.append(times)
    return times_by_provider

def get_folders_by_chunk(out_folder,starttime,endtime):
    st = starttime.strftime("%Y%m%dT%H%M%S")
    et = endtime.strftime("%Y%m%dT%H%M%S")
    chunk_name = st+"__"+et
    chunk_dir = os.path.join(out_folder,chunk_name)

    downloads_dir = os.path.join(chunk_dir,'downloads')
    metadata_dir = os.path.join(chunk_dir,'metadata')
    detections_dir = os.path.join(chunk_dir,'detections')
    asso_dir = os.path.join(chunk_dir,'associations')
    loc_dir = os.path.join(chunk_dir,'locations')
    events_dir = os.path.join(chunk_dir,'events')

    return {"metadata":metadata_dir,
            "downloads":downloads_dir,
            "detections":detections_dir,
            "associations":asso_dir,
            "locations":loc_dir,
            "events":events_dir}

def sanitize_pick_batch_size(pickers,download_args):
    overlaps = []
    batch_sizes = []
    for picker,args in pickers.items():
        batch_sizes.append(args.batch_size)
        overlaps.append(args.overlap)

    download_args["pick_batch_size"] = (min(overlaps),min(batch_sizes))
    return download_args

def sanitize_downloads(pickers):
    new_pickers = {}
    for i,(picker,args) in enumerate(pickers.items()):
        if i == (len(pickers.keys())-1):
            pass
        else:
            args.rm_download = False
        new_pickers[picker] = args
    return new_pickers


class SeisMonitor():
    def __init__(self,providers,out_folder,
                chunklength_in_sec=3600):
        self.providers = providers
        self.out_folder = out_folder
        self.chunklength_in_sec = chunklength_in_sec

        self.download_folder = os.path.join(out_folder,"downloads")
        self.pick_folder = os.path.join(out_folder,"picks")
        self.association_folder = os.path.join(out_folder,"asso")
        self.location_folder = os.path.join(out_folder,"loc")
        self.mag_folder = os.path.join(out_folder,"mag")

        self.process = {}

    def add_downloader(self,
                    threshold= 60,
                    overlap_in_sec=0,
                    pick_batch_size= (20,0.3),
                    groupby='{network}.{station}.{channel}',
                    n_processor=None):
        dld_args = locals().copy()
        dld_args["chunklength_in_sec"] = self.chunklength_in_sec
        dld_args.pop("self")
        self.process["download"] = dld_args
        
    def add_picker(self,
                    pickers={}):
        if pickers:
            pickers = sanitize_downloads(pickers)
            self.process["pick"] = pickers
            if "download" in list(self.process.keys()):
                self.process["download"] = sanitize_pick_batch_size(pickers,self.process["download"])

    def add_associator(self,
                        associators={}):
        if associators:
            self.process["associator"] = associators


    def add_locator(self,
                    locators={}
                    ):
        if locators:
            self.process["locator"] = locators

    def run(self):
        
        preproc_providers = get_preproc_providers(self.providers,
                                            self.chunklength_in_sec,
                                            self.out_folder)

        for chunk_provider in preproc_providers:
            print("chunk:",chunk_provider["providers"][0].waveform_restrictions.starttime,
                "--",chunk_provider["providers"][0].waveform_restrictions.endtime)
            providers = chunk_provider["providers"]
            folders = chunk_provider["folders"]

            # for provider in providers:
            #     wav = provider.waveform_restrictions
            #     print(provider.__dict__)
            
            # exit()

            for process, process_args in self.process.items():

                if process == "download":
                    structure = os.path.join("{station}","{network}.{station}.{location}.{channel}__{starttime}__{endtime}.mseed")
                    download_path = os.path.join(folders["downloads"],structure)
                    md = MseedDownloader(providers)
                    md.make_inv_and_json(folders["metadata"])
                    md.download(download_path,**process_args)
                    del md

                elif process == "pick":
                    for picker,picker_args in process_args.items():
                        out_path = os.path.join(folders["detections"],picker)
                        if picker == "EQTransformer":
                            _picker = ai_picker.EQTransformer(picker_args)
                            result = _picker.pick(folders["downloads"],
                                                            folders["metadata"],
                                                            out_path)
                            if result.empty:
                                print("No picks")
                                exit()
                            del _picker
                            del result

                        elif picker == "PhaseNet":
                            _picker = ai_picker.PhaseNet(picker_args)
                            result = _picker.pick(folders["downloads"],
                                                        folders["metadata"],
                                                        out_path)
                            if result.empty:
                                print("No picks")
                                exit()
                            del _picker
                            del result
                            
                elif process == "associator":
                    inv = os.path.join(folders["metadata"],"inv.xml")

                    for picker_path in glob.glob(os.path.join(folders["detections"],"*")):
                        picker_name = os.path.basename(picker_path)
                        picks_path = os.path.join(picker_path,"results",
                                                "seismonitor_picks.csv")
                        for associator,associator_args in process_args.items():
                            out_folder = os.path.join(folders["associations"],f"{associator}2{picker_name}")
                            if associator == "GaMMA":
                                _associator = ai_asso.GaMMA(associator_args)
                                _,result,_ = _associator.associate(picks_path,
                                                            inv,out_folder)
                                if result.empty:
                                    print("No associated picks")
                                    exit()

            #     # elif process == "locator":






                
        
        
        




        # self.json_path = os.path.join(self.download_folder,"json",
        #                                             "stations.json")
        # self.mseed_folder = os.path.join(self.download_folder,"mseed")
        # if object.name == "EQTransformer":
        #     picker = EQTransformer(self.mseed_storage,
        #                            self.json_path,out_dir)

# if __name__ == "__main__":
