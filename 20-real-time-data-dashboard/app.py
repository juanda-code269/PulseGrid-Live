from abc import ABC,abstractmethod
from datetime import datetime,timezone
import logging
import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="LivePipe Dashboard",page_icon="🛰️",layout="wide")
st.title("LivePipe — reusable real-time data architecture")
st.caption("Adapters fetch, validate, transform, cache, and display public data through one contract.")
logging.basicConfig(level=logging.INFO);logger=logging.getLogger("livepipe")


class Adapter(ABC):
    name="base"
    @abstractmethod
    def fetch_data(self):...
    @abstractmethod
    def validate_data(self,raw):...
    @abstractmethod
    def transform_data(self,raw):...
    def display_data(self,data):
        current=float(data.value.iloc[-1]);previous=float(data.value.iloc[-2]);change=current-previous;pct=change/previous if previous else np.nan
        a,b,c,d=st.columns(4);a.metric("Current",f"{current:,.2f} {data.unit.iloc[-1]}");b.metric("Previous",f"{previous:,.2f}");c.metric("Absolute change",f"{change:+,.2f}");d.metric("Percent change",f"{pct:+.2%}")
        st.plotly_chart(px.line(data,x="timestamp",y="value",title=f"Historical trend — {self.name}",markers=True),width="stretch")


class WeatherAdapter(Adapter):
    name="Open-Meteo weather"
    cities={"New York":(40.71,-74.01),"Miami":(25.76,-80.19),"London":(51.51,-.13),"Tokyo":(35.68,139.69)}
    def __init__(self,city):self.city=city
    def fetch_data(self):
        lat,lon=self.cities[self.city];url="https://api.open-meteo.com/v1/forecast";params={"latitude":lat,"longitude":lon,"hourly":"temperature_2m","past_days":2,"forecast_days":1,"timezone":"auto"}
        r=requests.get(url,params=params,timeout=10);r.raise_for_status();return r.json(),r.url
    def validate_data(self,raw):
        if not isinstance(raw,dict) or "hourly" not in raw or not {"time","temperature_2m"}.issubset(raw["hourly"]):raise ValueError("Malformed Open-Meteo response")
        if len(raw["hourly"]["time"])<2:raise ValueError("Open-Meteo returned insufficient history")
    def transform_data(self,raw):
        d=pd.DataFrame({"timestamp":pd.to_datetime(raw["hourly"]["time"]),"value":pd.to_numeric(raw["hourly"]["temperature_2m"],errors="coerce")}).dropna();d["unit"]="°C";return d[d.timestamp<=pd.Timestamp.now().tz_localize(None)].tail(48)


class CryptoAdapter(Adapter):
    name="CoinGecko crypto"
    def __init__(self,coin):self.coin=coin
    def fetch_data(self):
        url=f"https://api.coingecko.com/api/v3/coins/{self.coin}/market_chart";r=requests.get(url,params={"vs_currency":"usd","days":"1","interval":"hourly"},timeout=10);r.raise_for_status();return r.json(),r.url
    def validate_data(self,raw):
        if not isinstance(raw,dict) or "prices" not in raw or len(raw["prices"])<2:raise ValueError("Malformed or rate-limited CoinGecko response")
    def transform_data(self,raw):
        d=pd.DataFrame(raw["prices"],columns=["timestamp","value"]);d.timestamp=pd.to_datetime(d.timestamp,unit="ms",utc=True);d["unit"]="USD";return d


class DemoAdapter(Adapter):
    name="Offline demo sensor"
    def __init__(self,channel):self.channel=channel
    def fetch_data(self):
        rng=np.random.default_rng(abs(hash(self.channel))%2**32);times=pd.date_range(end=pd.Timestamp.now().floor("min"),periods=120,freq="min");values=50+np.cumsum(rng.normal(0,.35,len(times)))+3*np.sin(np.arange(len(times))/12);return {"times":[x.isoformat() for x in times],"values":values.tolist()},"Generated locally"
    def validate_data(self,raw):
        if not isinstance(raw,dict) or len(raw.get("times",[]))!=len(raw.get("values",[])) or len(raw.get("times",[]))<2:raise ValueError("Malformed demo response")
    def transform_data(self,raw):return pd.DataFrame({"timestamp":pd.to_datetime(raw["times"]),"value":raw["values"],"unit":"units"})


def make_adapter(kind,option):
    return WeatherAdapter(option) if kind=="Weather" else CryptoAdapter(option) if kind=="Crypto" else DemoAdapter(option)


@st.cache_data(ttl=300,show_spinner=False)
def fetch_cached(kind,option):
    adapter=make_adapter(kind,option);raw,url=adapter.fetch_data();adapter.validate_data(raw);data=adapter.transform_data(raw)
    if not {"timestamp","value","unit"}.issubset(data) or len(data)<2 or not np.isfinite(data.value).all():raise ValueError("Adapter transformation failed the standard data contract")
    return data,url,datetime.now(timezone.utc).isoformat()


kind=st.sidebar.selectbox("Adapter",["Weather","Crypto","Demo sensor"])
if kind=="Weather":option=st.sidebar.selectbox("City",list(WeatherAdapter.cities))
elif kind=="Crypto":option=st.sidebar.selectbox("Asset",["bitcoin","ethereum"])
else:option=st.sidebar.selectbox("Channel",["alpha","beta","gamma"])
if st.sidebar.button("Refresh now",type="primary"):fetch_cached.clear();st.rerun()
try:
    data,url,fetched=fetch_cached(kind,option);status="Live public data" if kind!="Demo sensor" else "Generated demo data"
except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
    logger.exception("adapter failure");st.error(f"Data service unavailable or invalid: {exc}");st.info("Switch to Demo sensor to inspect the dashboard without a network connection.");st.stop()
adapter=make_adapter(kind,option);st.success(f"{status} • cache TTL 5 minutes • fetched {fetched}");adapter.display_data(data)
st.dataframe(pd.DataFrame({"Field":["Source","Adapter","Last fetched (UTC)","Latest observation","Rows"],"Value":[str(url),adapter.name,fetched,str(data.timestamp.max()),str(len(data))]}),width="stretch",hide_index=True)

with st.expander("Architecture and adding a new API",expanded=True):
    st.code('''class MyAdapter(Adapter):
    name = "My public source"
    def fetch_data(self):
        # Request with a timeout; return (raw_payload, source_url)
        ...
    def validate_data(self, raw):
        # Raise ValueError on missing fields, wrong types, or empty data
        ...
    def transform_data(self, raw):
        # Return timestamp, value, unit columns
        ...''',language="python")
    st.write("Register the adapter in `make_adapter()`. The standard display, caching, refresh, validation, error boundary, timestamp, and source table then work without rewriting the interface.")
    st.markdown("**Failure behavior:** requests have timeouts; HTTP errors, malformed JSON contracts, non-finite values, short histories, and unavailable services stop with a visible message instead of silently drawing an incorrect chart. Python logging records the exception for operators. Cached and live status is shown explicitly.")
