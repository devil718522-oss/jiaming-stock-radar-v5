import streamlit as st
import pandas as pd, numpy as np, requests
from datetime import date,timedelta

st.set_page_config(page_title="家銘台股雷達 V5",page_icon="📡",layout="wide")
st.title("📡 家銘台股雷達 V5 Alpha｜多因子決策系統")
st.caption("股票品質 ≠ 現在買點｜技術＋籌碼＋基本面＋市場環境＋風險否決器")
API="https://api.finmindtrade.com/api/v4/data"
DEFAULT="""2330
2317
2454
2303
2382
3231
2379
3034
3711
2409
3481
2344
2603
2609
2002
1301
1303
2881
2882
2886"""

def call(ds,sid,start,end,token):
    q={"dataset":ds,"data_id":sid,"start_date":str(start),"end_date":str(end)}
    h={"Authorization":f"Bearer {token}"} if token else {}
    r=requests.get(API,params=q,headers=h,timeout=30);r.raise_for_status()
    return pd.DataFrame(r.json().get("data",[]))

@st.cache_data(ttl=3600,show_spinner=False)
def price(sid,start,end,token):
    d=call("TaiwanStockPrice",sid,start,end,token)
    if d.empty:return d
    d["date"]=pd.to_datetime(d.date)
    d=d.sort_values("date").rename(columns={"close":"Close","Trading_Volume":"Volume"})
    d["Close"]=pd.to_numeric(d.Close,errors="coerce");d["Volume"]=pd.to_numeric(d.Volume,errors="coerce")
    return d.dropna(subset=["Close"]).reset_index(drop=True)

@st.cache_data(ttl=21600,show_spinner=False)
def inst(sid,start,end,token):
    try:
        d=call("TaiwanStockInstitutionalInvestorsBuySell",sid,start,end,token)
        if not d.empty:d["date"]=pd.to_datetime(d.date)
        return d
    except:return pd.DataFrame()

@st.cache_data(ttl=21600,show_spinner=False)
def rev(sid,start,end,token):
    try:
        d=call("TaiwanStockMonthRevenue",sid,start,end,token)
        if not d.empty and "date" in d:d["date"]=pd.to_datetime(d.date)
        return d
    except:return pd.DataFrame()

def feat(d):
    x=d.copy()
    for n in [5,10,20,60,120,200]:x[f"MA{n}"]=x.Close.rolling(n).mean()
    x["VR"]=x.Volume/x.Volume.rolling(20).mean();x["R20"]=x.Close.pct_change(20);x["R60"]=x.Close.pct_change(60)
    x["HH20"]=x.Close.rolling(20).max()
    delta=x.Close.diff();g=delta.clip(lower=0).rolling(14).mean();l=(-delta.clip(upper=0)).rolling(14).mean()
    x["RSI"]=100-100/(1+g/l.replace(0,np.nan))
    e12=x.Close.ewm(span=12,adjust=False).mean();e26=x.Close.ewm(span=26,adjust=False).mean()
    x["MACD"]=e12-e26;x["SIG"]=x.MACD.ewm(span=9,adjust=False).mean()
    return x

def tech(x):
    r=x.iloc[-1];s=0;w=[]
    checks=[(r.Close>r.MA20,4,"站上20MA"),(r.MA5>r.MA10>r.MA20,5,"短中期多頭排列"),
            (r.MA20>r.MA60,4,"20MA>60MA"),(r.MA60>r.MA120,3,"中期趨勢偏多"),
            (r.MA20>x.MA20.iloc[-6],3,"20MA上彎"),(r.R20>.03,3,"20日動能正向"),
            (r.R60>.08,2,"60日動能強"),(r.Close>=r.HH20*.98,2,"接近20日高"),
            (r.VR>=1.2,2,"量能放大"),(50<=r.RSI<=70,1,"RSI健康"),(r.MACD>r.SIG,1,"MACD偏多")]
    for ok,p,msg in checks:
        if bool(ok):s+=p;w.append(msg)
    return min(s,30),w

def chip(d):
    if d.empty:return 15,["籌碼資料不足：中性暫估"],False
    buy=[c for c in d if "buy" in c.lower()];sell=[c for c in d if "sell" in c.lower()]
    if not buy or not sell:return 15,["籌碼欄位不足：中性暫估"],False
    for c in buy+sell:d[c]=pd.to_numeric(d[c],errors="coerce")
    z=d.groupby("date")[buy].sum().sum(axis=1)-d.groupby("date")[sell].sum().sum(axis=1)
    s=0;w=[]
    for ok,p,msg in [(z.tail(5).sum()>0,10,"近5日法人淨買"),(z.tail(10).sum()>0,8,"近10日法人淨買"),
                     ((z.tail(5)>0).sum()>=3,7,"法人買盤具連續性"),(z.tail(20).sum()>0,5,"近20日籌碼偏多")]:
        if ok:s+=p;w.append(msg)
    return min(s,30),w,True

def fundamental(d):
    if d.empty:return 12,["基本面資料不足：中性暫估"],False
    cols=[c for c in d if "revenue" in c.lower() and c.lower()!="revenue_month"]
    if not cols:return 12,["營收欄位不足：中性暫估"],False
    c=cols[0];z=d.copy();z[c]=pd.to_numeric(z[c],errors="coerce");z=z.dropna(subset=[c]).sort_values("date")
    if len(z)<13:return 12,["營收歷史不足：中性暫估"],False
    yoy=z[c].iloc[-1]/z[c].iloc[-13]-1;mom=z[c].iloc[-1]/z[c].iloc[-2]-1;s=8;w=[f"營收YoY {yoy:.1%}",f"營收MoM {mom:.1%}"]
    s+=10 if yoy>.2 else 7 if yoy>.1 else 4 if yoy>0 else 0
    if mom>0:s+=4
    return min(s,25),w,True

def market(d):
    if d.empty or len(d)<200:return 7,["市場資料不足"]
    x=feat(d);r=x.iloc[-1];s=0;w=[]
    for ok,p,msg in [(r.Close>r.MA20,4,"市場>20MA"),(r.Close>r.MA60,4,"市場>60MA"),(r.MA20>r.MA60,4,"市場中期多頭"),(r.MA60>r.MA200,3,"市場長期偏多")]:
        if bool(ok):s+=p;w.append(msg)
    return min(s,15),w

def grade(s):return "S" if s>=85 else "A" if s>=75 else "B" if s>=65 else "C"

def gate(x,total):
    r=x.iloc[-1];g5=r.Close/r.MA5-1;flags=[];status="🟢 可觀察"
    if g5>.08:flags.append(f"5MA乖離 {g5:.1%}");status="🔴 過熱，不追價"
    if r.R20>.30:flags.append(f"20日漲幅 {r.R20:.1%}");status="🔴 過熱，不追價"
    if r.RSI>78:flags.append(f"RSI {r.RSI:.0f}");status="🔴 過熱，不追價"
    if r.Close<r.MA20:flags.append("跌破20MA");status="🟡 等待重新轉強"
    if total<65:status="⚪ 未進雷達"
    return status,flags,g5

with st.sidebar:
    token=st.text_input("FinMind Token",type="password")
    days=st.slider("技術資料天數",300,800,500,50)
    st.caption("Alpha 版先完成評分骨架；V5.1 再加入 EPS/ROE/毛利率、融資券與訊號資料庫。")
stocks=[x.strip() for x in st.text_area("股票池｜一行一個代號",DEFAULT,height=220).splitlines() if x.strip()]

if st.button("📡 啟動 V5 雷達",type="primary",use_container_width=True):
    end=date.today();start=end-timedelta(days=days)
    try:m=price("0050",start,end,token)
    except:m=pd.DataFrame()
    ms,mw=market(m);rows=[];detail={};bar=st.progress(0)
    for i,sid in enumerate(stocks):
        try:
            p=price(sid,start,end,token)
            if len(p)<150:continue
            x=feat(p).dropna().reset_index(drop=True);ts,tw=tech(x)
            cs,cw,cok=chip(inst(sid,end-timedelta(days=45),end,token))
            fs,fw,fok=fundamental(rev(sid,end-timedelta(days=500),end,token))
            total=ts+cs+fs+ms;status,flags,g5=gate(x,total);r=x.iloc[-1]
            rows.append([sid,total,grade(total),ts,cs,fs,ms,r.Close,g5,r.R20,status,"✓" if cok else "△","✓" if fok else "△"])
            detail[sid]=(tw,cw,fw,flags)
        except Exception:pass
        bar.progress((i+1)/len(stocks),text=f"分析 {i+1}/{len(stocks)}")
    bar.empty()
    if not rows:st.error("沒有成功取得資料。");st.stop()
    out=pd.DataFrame(rows,columns=["代號","總分","級別","技術","籌碼","基本","環境","最新價","5MA乖離","20日漲跌","狀態","籌碼資料","基本資料"]).sort_values(["總分","技術"],ascending=False)
    show=out.copy()
    for c in ["5MA乖離","20日漲跌"]:show[c]=show[c].map(lambda v:f"{v:.1%}")
    st.subheader("🏆 今日多因子雷達");st.dataframe(show,use_container_width=True,hide_index=True)
    st.subheader("🎯 Top 雷達候選")
    for _,r in out[out.總分>=65].head(10).iterrows():
        tw,cw,fw,flags=detail[r.代號]
        with st.expander(f'{r.級別}｜{r.代號}｜{int(r.總分)}/100｜{r.狀態}'):
            a,b,c,d=st.columns(4);a.metric("技術",f"{r.技術}/30");b.metric("籌碼",f"{r.籌碼}/30");c.metric("基本",f"{r.基本}/25");d.metric("環境",f"{r.環境}/15")
            st.write("技術："+("、".join(tw) if tw else "無加分"))
            st.write("籌碼："+("、".join(cw) if cw else "無加分"))
            st.write("基本："+("、".join(fw) if fw else "無加分"))
            if flags:st.warning("風險否決器："+"、".join(flags))
st.caption("V5 Alpha｜研究用途，不構成投資建議。△ 代表該模組資料不足，暫採中性分數，避免誤判。")
