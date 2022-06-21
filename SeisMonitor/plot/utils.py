from concurrent.futures import process
from obspy.clients.fdsn import Client
from obspy.core.utcdatetime import UTCDateTime
from obspy.realtime.signal import scale
# from obspy.core.stream import Stream
import concurrent.futures as cf
import matplotlib.pyplot as plt
import matplotlib.cm     as cm
import datetime as dt
import pandas as pd
import numpy as np
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.gridspec as gs
import matplotlib.dates as mdates
from obspy.geodetics.base import gps2dist_azimuth
from SeisMonitor.monitor.downloader import utils as dld_ut
def order_by_coord(coord,picks):
    lat,lon = coord
    
    # data = {"station":stas,"latitude":lats,"longitude":lons}
    # df = pd.DataFrame.from_dict(data)

    gps2da_gen = lambda y: gps2dist_azimuth(y.station_lat,y.station_lon,lat,lon)
    gps2da = picks.apply(gps2da_gen,axis=1).tolist()
    picks[["r","az","baz"]] = pd.DataFrame(gps2da)
    picks["r"] = picks["r"]/1e3

    picks = picks.drop_duplicates(subset=["station"],
                                ignore_index=True)
    picks = picks.sort_values("r",ignore_index=True,ascending=False)
    picks = picks[["station","r"]]
    picks['id'] = picks.index
    # print(df)
    return df

def get_ordered_streams(providers,order,
                        starttime,endtime,
                        n_processor=None):
    ordered_info,providers = get_ordered_info(providers,order)

    def get_client_waveforms_by_thread(netsta):
        strid = ".".join(netsta)
        bulk = (netsta[0],netsta[1],waveform_restrictions.location,
                waveform_restrictions.channel,starttime,endtime)
        st,_,_ = dld_ut.get_client_waveforms(client,bulk,
                                waveform_restrictions,
                                processing  )
        if len(st)==0:
            return 

        return (strid,st)

    for provider in providers:
        provider.waveform_restrictions.starttime = starttime
        provider.waveform_restrictions.endtime = endtime
        client = provider.client
        waveform_restrictions = provider.waveform_restrictions
        bulk_info = waveform_restrictions.bulk_info
        processing = provider.processing

        if n_processor == 1:
            result = []
            for netsta in waveform_restrictions.bulk_info:
                st = get_client_waveforms_by_thread(netsta)
                result.append(st)
        else:
            with cf.ThreadPoolExecutor(n_processor) as executor:
                result = executor.map(get_client_waveforms_by_thread,bulk_info)
                result = list(result)
        
        result = list(filter(None, result))
        result = dict(list(result))

    st_keys = list(result.keys())        

    streams = {}
    for netsta,row in ordered_info.iterrows():
        strid = ".".join(netsta)

        if strid in st_keys:
            st = result[strid]
        else:
            print("no",strid)
            continue

        streams[strid] = st

    # print(streams)

    return streams
        
def get_ordered_info(providers,order):
    inv,json_info,providers,sod = dld_ut.get_merged_inv_and_json(providers)
    
    json_info = pd.DataFrame.from_dict(json_info, orient='index')
    json_info["station"] = json_info.index
    json_info = json_info.set_index(["network","station"])

    if order == None:
        return json_info
    elif isinstance(order[0],str):
        lat,lon,_ = json_info.loc[order,"coords"]
    elif isinstance(order[0],float):
        lat,lon = order

    # json_info = json_info.reset_index(drop=True)
    distance_func = lambda y: gps2dist_azimuth(y[0],y[1],lat,lon)[0]
    json_info["r"] = json_info["coords"].apply(distance_func)
    
    json_info = json_info.sort_values(by="r")
    return json_info,providers



### multiple picker trace
def get_picks(csv,starttime=None,endtime=None,
                select_networks=[],select_stations=[],
                filter_networks=[],filter_stations=[]):
    "filter dataframe data"

    df = pd.read_csv(csv,parse_dates=['arrival_time'])

    if isinstance(starttime, UTCDateTime):
        starttime = starttime.datetime
    if isinstance(endtime, UTCDateTime):
        endtime = endtime.datetime

    if isinstance(df["arrival_time"].dtype, pd.core.dtypes.dtypes.DatetimeTZDtype):
        raise Exception("revise el dataframe. quitele el +00:00")
        # sed -i 's/+00:00,/,/g' /mnt/almacenamiento/ecastillo/data/multiple_picker_trace/phasenet.csv
    else:
        pass

    if starttime != None:
        df = df[df["arrival_time"] >= starttime ]
    if endtime != None:
        df = df[df["arrival_time"] <= endtime ]

    if select_networks:
        df = df[ df["network"].isin(select_networks) ]
    if select_stations:
        df = df[ df["station"].isin(select_stations) ]
    if filter_networks:
        df = df[ ~df["network"].isin(filter_networks) ]
    if filter_stations:
        df = df[ ~df["station"].isin(filter_stations) ]
    
    return df

def get_proc_tr(st,
        processing=None):
    "returns the first processed trace"
    
    if processing == None:
        processed = False
        comment = ""
    else:
        st,processed, comment = processing.run(st) 

    st.trim(min([tr.stats.starttime for tr in st]),
             max([tr.stats.endtime for tr in st]), 
             pad=True, fill_value=0)
    tr = st[0]
    return tr

def get_multiple_picker_figure(n_pickers,tr_h = 0.7):
    fig = plt.figure(figsize=(12,12))
    gs1 = gs.GridSpec(1, 1, figure=fig)
    gs1.update(left=0.12, right=0.9, wspace=0.05)

    picker_h = 1 - tr_h
    picker_r = [round(x/n_pickers,3) for x in [picker_h]*n_pickers]
    height_ratios = [tr_h] + picker_r

    gss = gs.GridSpecFromSubplotSpec(len(height_ratios), 1,subplot_spec=gs1[0], hspace=0.0,
                                    height_ratios=height_ratios)

    ax0 = fig.add_subplot(gss[0])
    ax0.tick_params(axis="x", labelbottom=0)
    ax0.set_yticks([])
    time_axes = [ax0]
    for i in range(1,len(height_ratios)):
        ax = fig.add_subplot(gss[i],sharex=ax0)

        if i != len(height_ratios) -1:
            ax.tick_params(axis="x", labelbottom=0)

        ax.set_yticks([])
        time_axes.append(ax)

    fig.autofmt_xdate()


    gs2 = gs.GridSpec(1, 1)
    gs2.update(left=0.92, right=0.96, hspace=0.2)
    gss2 = gs.GridSpecFromSubplotSpec(1, 2,subplot_spec=gs2[0], hspace=0.5,width_ratios=[1,1])
    ax4 = fig.add_subplot(gss2[0])
    ax4.set_yticks([])
    ax4.set_xticks([])
    ax5 = fig.add_subplot(gss2[1],sharey=ax4)
    ax5.set_yticks([])
    ax5.set_xticks([])
    ax5.text(1.1,0.5,"Probability", size=10,
            verticalalignment='center', rotation=270)

    prob_axes = [ax4,ax5]
    return fig, time_axes, prob_axes

def plot_multiple_picker(st,info,
                        processing = None,
                        tr_h =0.7
                        ):

    len_pickers = len(list(info.keys()))
    fig,ax,pax = get_multiple_picker_figure(len_pickers,tr_h)

    len_axes = len(ax)

    tr = get_proc_tr(st,processing )

    network = tr.stats.network
    station = tr.stats.station
    location = tr.stats.location
    channel = tr.stats.channel
    starttime = tr.stats.starttime
    endtime = tr.stats.endtime
    STARTTIME = mdates.date2num(starttime.datetime)

    x = tr.times("matplotlib")-STARTTIME
    ax[0].plot(x, tr.data, "k-")
    text = ".".join((network,station,
                 
                    location,channel))
    text = text.rjust(len(text) + 18)
    text += "\nstarttime: " + starttime.strftime("%Y-%m-%d %H:%M:%S.%f")+\
            "\nendtime : " + endtime.strftime("%Y-%m-%d %H:%M:%S.%f")

    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    # ax[0].text(.03, .95, text,
    ax[0].text(0.72, 0.13, text,
                horizontalalignment='left',
                verticalalignment='top',
                transform=ax[0].transAxes,
                backgroundcolor= "white",
                fontdict={"fontsize":9},
                bbox=props)
    ax[0].xaxis_date()
    ax[0].set_xlim([min(x),max(x)])
    ymin, ymax = ax[0].get_ylim()

    ax[len_axes-1].set_xlabel(f"dt", size=16)

    # https://stackoverflow.com/questions/8342549/matplotlib-add-colorbar-to-a-sequence-of-line-plots
    # Pcmap = cm.winter.reversed()
    # Scmap = cm.autumn.reversed()
    # Pcmap = cm.get_cmap("winter",10)
    Pcmap = cm.get_cmap("Blues",10)
    # Pcmap = Pcmap.reversed()
    Scmap = cm.get_cmap("Reds",10)
    # Scmap = Scmap.reversed()
    for i,(picker,csv) in enumerate(info.items(),1):
        df = get_picks(csv,starttime,endtime,
                        select_stations=[tr.stats.station])
        for j, (_, row) in enumerate(df.iterrows()):
            pick = mdates.date2num(row['arrival_time'])-STARTTIME
            if row['phasehint'].upper() == 'P':
                color = Pcmap(row['probability']-0.001) # -0.001 removes a bug in Cbar 
            elif row['phasehint'].upper() == 'S':
                color = Scmap(row['probability']-0.001)

            ax[i].vlines(pick, ymin, ymax, color=color, 
                            # linewidth=0.7, 
                            linewidth=1, 
                            label=row['phasehint'])
            ax[i].set_facecolor('lightgray')
            ax[i].set_yticks([])
            ax[i].set_ylabel(picker,rotation=0,labelpad=24,fontsize=16)

    fig.autofmt_xdate()

    Pclb = fig.colorbar(cm.ScalarMappable(cmap=Pcmap), cax=pax[0],orientation="vertical")
    Pclb.ax.tick_params(labelsize=1)
    Pclb.ax.set_title('P',fontsize=18)
    Sclb = fig.colorbar(cm.ScalarMappable(cmap=Scmap), cax=pax[1],orientation="vertical")
    Sclb.ax.set_title('S',fontsize=18)
    # Sclb.ax.set_title('Probability',fontsize=10)

    fig.autofmt_xdate()
    return fig


if __name__ == "__main__":
    # client = Client(base_url='http://10.100.100.232:8091')
    client = Client(base_url='http://sismo.sgc.gov.co:8080/')
    # starttime = UTCDateTime("20191224T185959")
    starttime = UTCDateTime("20191224T190600")
    endtime = UTCDateTime("20191224T191359")
    st = client.get_waveforms(network="CM",station="URMC",
                                    location="*",
                                    channel="HHZ",
                                    starttime=starttime,
                                    endtime=endtime)

    eqt_csv = "/home/emmanuel/EDCT/test/picks/eqt/seismonitor_picks.csv"
    sgc_csv = "/home/emmanuel/EDCT/test/picks/eqt/seismonitor_picks.csv"
    phasenet_csv = "/home/emmanuel/EDCT/test/picks/eqt/seismonitor_picks.csv"
    # csvs = [eqt_csv,sgc_csv,phasenet_csv]
    csvs = {"EQT":eqt_csv,"PNET":phasenet_csv,"SGC":sgc_csv}

    # df = get_picks(phasenet_csv,starttime,endtime)
    # print(df)
    fig = plot_multiple_picker(st,csvs)
    fig.savefig("/home/emmanuel/EDCT/SeisMonitor/SeisMonitor/plot/mpt.png",dpi=300)