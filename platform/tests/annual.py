"""Reconciliation cases for the local annual books, using fictional vouchers."""
from decimal import Decimal as D
from types import SimpleNamespace as Row
from service.books import calculate

def project(i):
    return Row(id=i,code=f"P{i}",name=f"项目{i}",details={"category":"自主"})

def fee(pid,amount,kind="直接投入",year=2025,mode="费用化",special="一般",line=8):
    return Row(project=pid,payload={"day":f"{year}-05-08","type":special,"amount":str(amount),"category":kind,
        "treatment":mode,"voucher":f"P{pid}-{amount}","subject":"费用","note":"试验","positive":True,"hightech":True,"basis":"测试凭证","tax_line":line})

def check():
    ps=[project(1),project(2)]
    fees=[fee(1,900),fee(2,500,"其他相关",line=29),fee(2,100,"境内委托",line=None),fee(2,2000,"境外机构委托",line=None),fee(1,99,"境外个人委托",line=None),fee(1,1500,special="产品材料冲减")]
    r=calculate(2025,ps,fees,[],D(0),D(100));m=r["mapping"]
    assert m["34"]==100 and m["38"]==720 and m["40"]==1800 and m["51"]==300
    assert all(r["checks"].values())
    fees=[fee(1,50),fee(1,80,special="产品材料冲减")]
    r=calculate(2025,ps,fees,[],D(0),D(100))
    assert r["mapping"]["51"]==0 and r["carry"]==30
    r=calculate(2026,ps,fees+[fee(1,80,year=2026)],[],r["carry"],D(100))
    assert r["mapping"]["49"]==30 and r["mapping"]["51"]==50
    cap=[fee(1,400,mode="资本化",year=2024),fee(1,600,mode="资本化",year=2025)]
    ann=[Row(project=1,payload={"year":2025,"formed":"2025-06-01","amortization":"50","opening_material":"0"})]
    r=calculate(2025,ps,cap,ann,D(0),D(100))
    assert r["mapping"]["42"]==1000 and r["mapping"]["43"]==50 and r["mapping"]["51"]==50
    print("PASS pooled other expense, foreign outsourcing cap, product carry, capitalized expenditure and amortization",flush=True)
if __name__=="__main__":check()
