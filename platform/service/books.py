"""Annual working papers, in cents, with traceable voucher and return-line totals."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter,Request
from pydantic import Field
from sqlalchemy import Column,ForeignKey,JSON,String,select

from .auth import Actor,DB,Form,fail,ok,record,require
from .db import Base,ID,Entry,Project,Task,now
from .finance import CATEGORIES,Money,WorkBase,amounts,business_task,cent,distribute,finish,save,write_xlsx
from .materials import deliver,project_for
from .workflow import object_info,visible_customer

router=APIRouter()
ZERO=Decimal(0)
FORM_SOURCE="https://12366.chinatax.gov.cn/bzds/037/037.html"
LABEL={1:"享受项目数",2:"自主、合作、集中研发合计",3:"人员人工",7:"直接投入",16:"折旧",19:"摊销",23:"设计及其他试验",28:"其他相关费用发生额",34:"其他相关费用限额调整后",35:"委托研发发生额",36:"境内委托发生额",37:"境外机构委托发生额",38:"境外机构允许金额",39:"境外个人委托发生额",40:"年度研发费用小计",41:"费用化金额",42:"资本化金额",43:"本年形成资产的本年税前摊销额",44:"以前年度形成资产本年税前摊销额",45:"允许扣除费用",46:"特殊收入",47:"抵减特殊收入后",48:"本年产品对应材料",49:"上年结转产品材料",50:"经复核适用的加计比例",51:"本年加计额",52:"产品材料结转以后年度"}
class Annual(WorkBase):
    project:int
    year:int=Field(ge=2015,le=2099)
    formed:date|None=None
    amortization:Money=Decimal(0)
    opening_material:Money=Decimal(0)
    basis:str=Field(min_length=1,max_length=800)

@router.post("/annual-inputs")
def annual(form:Annual,request:Request,db:DB,u:Actor):
    t=business_task(db,u,form.task);p=project_for(db,t,form.project)
    if t.line!="finance":fail(403,"年度数据由财务承办")
    if form.amortization and (not form.formed or form.formed.year>form.year):fail(422,"请核对摊销的资产形成日期")
    form.key=f"YEAR/{p.id}/{form.year}"
    q=select(Entry.id).where(Entry.project==p.id,Entry.kind=="annual",Entry.key==form.key)
    if db.scalar(q):fail(409,"本项目该年度已有调整，请复核原单")
    return finish(db,u,request,save(db,u,t,"annual",form,p.id))

@router.get("/annual-inputs")
def annuals(db:DB,u:Actor):
    from .finance import workrows
    return ok([object_info(e) for e in workrows(db,u,"annual")])

class Ledger(Form):
    customer:int=Field(gt=0)
    year:int=Field(ge=2015,le=2099)
    edition:Literal["2015","2021"]="2021"
    rate:Literal["100","120","75","50"]="100"

class SavedBook(Base):
    __tablename__="fin_ledger_snapshot"
    id=Column(ID,primary_key=True)
    customer=Column(ID,ForeignKey("biz_customer.id"),nullable=False,index=True)
    actor=Column(ID,ForeignKey("sys_user.id"),nullable=False)
    period=Column(String(8),nullable=False)
    inputs=Column(JSON,nullable=False)
    payload=Column(JSON,nullable=False)

def gather(form,db,u):
    c=visible_customer(db,u,form.customer);require(u,"manager","director")
    if u.department!=c.department and u.id!=c.manager:fail(403,"完整年度汇总需客户管理权限")
    rows=list(db.execute(select(Entry,Task.status).join(Task,Task.id==Entry.task).where(Task.customer==c.id,Entry.kind.in_(["fee","annual"]))))
    items=[]
    for e,status in rows:
        year=e.payload.get("year") or int(e.payload["day"][:4])
        if year<=form.year:
            if status not in {"customer","complete","archived"}:fail(409,"期间内有待审核的费用或年度数据，请先完成所属任务内审")
            items.append(e)
    projects=list(db.scalars(select(Project).where(Project.customer==c.id).order_by(Project.id)))
    return c,projects,items

def calculate(year,projects,fees,annuals,carry,rate):
    byid={p.id:p for p in projects};ids=list(byid);actual=defaultdict(Decimal);hi=defaultdict(lambda:[ZERO]*9)
    buckets=defaultdict(lambda:[ZERO]*9);lines=defaultdict(Decimal);warnings=set();missing=set()
    special=defaultdict(Decimal);products=defaultdict(Decimal);grants=defaultdict(Decimal)
    details=[];split=defaultdict(Decimal);formed={}
    for e in annuals:
        if e.payload.get("formed"):formed[e.project]=int(e.payload["formed"][:4])
    for e in fees:
        p=e.payload;k=e.project;v=amounts(e,"amount");i=CATEGORIES.index(p["category"]);y=int(p["day"][:4]);typ=p["type"]
        cap=p["treatment"]=="资本化"
        if y==year:
            details.append([k,p["day"],p["voucher"],p["subject"],p["note"],p["category"],v,typ,p.get("basis",""),p["treatment"]])
            if typ=="特殊收入":special[k]+=v;continue
            if typ=="产品材料冲减":products[k]+=v;continue
            if typ=="不征税补助":grants[k]+=v;continue
            if typ=="试运行销售":warnings.add("试运行销售收入、成本须独立列报");continue
            actual[k]+=v
            if p["hightech"]:hi[k][i]+=v*(Decimal(".8") if i>=6 else 1)
        if typ in {"特殊收入","产品材料冲减","不征税补助","试运行销售"}:continue
        if cap and y<=year and k not in formed:warnings.add(byid[k].code+"：资本化支出尚无已确认的资产形成日期")
        if (cap and (formed.get(k)!=year or y>year)) or (not cap and y!=year):continue
        if not p["positive"] or typ in {"房屋折旧租赁","长期待摊"} or (typ=="共用" and not p["basis"]):
            warnings.add(p["voucher"]+"：按费用资格或分摊依据排除");continue
        buckets[k][i]+=v
        split[k,i,p["treatment"]]+=v
        if i<6:
            if p.get("tax_line"):lines[p["tax_line"]]+=v
            elif v:missing.add(p["voucher"])
    first=sum((sum(buckets[k][:5]) for k in ids),ZERO)
    weights={k:buckets[k][5] for k in ids}
    if year>=2021:other=distribute(min(sum(weights.values()),cent(first/9)),weights)
    else:other={k:min(weights[k],cent(sum(buckets[k][:5])/9)) for k in ids}
    domestic={k:cent(buckets[k][6]*Decimal(".8")) for k in ids}
    foreign={k:buckets[k][7] for k in ids}
    allowed=distribute(min(cent(sum(foreign.values())*Decimal(".8")),cent((first+sum(other.values())+sum(domestic.values()))*2/3)),foreign)
    h_other={k:hi[k][5] for k in ids}
    hi_limit=cent(sum((sum(hi[k])-hi[k][5] for k in ids),ZERO)/4)
    high_other=distribute(min(hi_limit,sum(h_other.values())),h_other)
    for i,r in enumerate([3,7,16,19,23,28]):lines[r]=sum(buckets[k][i] for k in ids)
    lines[34]=sum(other.values());lines[2]=first+lines[34]
    for i,r in enumerate([36,37,39],6):lines[r]=sum(buckets[k][i] for k in ids)
    lines[35]=lines[36]+lines[37]+lines[39];lines[38]=sum(allowed.values())
    result=[]
    for k in ids:
        b=buckets[k];eligible=list(b[:5])+[other[k],domestic[k],allowed[k],ZERO]
        base=sum(eligible);cap_total=ZERO
        for i,value in enumerate(eligible):
            share=distribute(value,{"资本化":split[k,i,"资本化"],"费用化":split[k,i,"费用化"]})
            cap_total+=share["资本化"]
        lines[42]+=cap_total;lines[41]+=base-cap_total
        project=byid[k];high=cent(sum(hi[k])-hi[k][5]+high_other[k])
        result.append(dict(id=k,code=project.code,name=project.name,category=project.details["category"],account=cent(actual[k]),
            hightech=high,deduction=base,capitalized=cap_total,expense=base-cap_total,other_allowed=other[k],
            domestic_allowed=domestic[k],foreign_allowed=allowed[k],offset=special[k]+products[k]+grants[k],categories=b,
            difference_high=high-cent(actual[k]),difference_tax=base-cent(actual[k])))
    entries=[e for e in annuals if e.payload["year"]==year]
    for e in entries:
        amount=amounts(e,"amortization");lines[43 if formed.get(e.project)==year else 44]+=amount
        if amounts(e,"opening_material") and carry:fail(409,"已有上年结转记录，不能再重复录入期初产品材料")
    lines[1]=len({r["id"] for r in result if r["deduction"]>0}|{e.project for e in entries if amounts(e,"amortization")})
    lines[40]=lines[41]+lines[42];lines[45]=lines[41]+lines[43]+lines[44]
    lines[46]=sum(special.values());lines[47]=max(ZERO,lines[45]-lines[46])
    lines[48]=sum(products.values());lines[49]=carry+sum((amounts(e,"opening_material") for e in entries),ZERO)
    balance=lines[47]-lines[48]-lines[49];lines[50]=rate/100;lines[51]=cent(max(ZERO,balance)*lines[50]);lines[52]=max(ZERO,-balance)
    if sum(grants.values()):warnings.add("已登记不征税补助，请逐笔确认关联的支出已标记不符合加计，避免重复冲减")
    if missing:warnings.add("凭证缺少申报明细行："+", ".join(sorted(missing)))
    checks={"项目与年度合计":sum((r["deduction"] for r in result),ZERO)==lines[40],
            "费用化与资本化":lines[40]==lines[2]+sum(domestic.values())+lines[38],
            "申报明细行完整":not missing,"补助关联已复核":not any(grants.values())}
    return dict(projects=result,details=details,warnings=sorted(warnings),checks=checks,
                mapping={str(r):cent(Decimal(lines[r])) for r in range(1,53)},carry=lines[52])

def report(form,db,u):
    c,projects,items=gather(form,db,u)
    annuals=[e for e in items if e.kind=="annual"];fees=[e for e in items if e.kind=="fee"]
    years={form.year,*[int(e.payload["day"][:4]) for e in fees],*[e.payload["year"] for e in annuals]}
    carry=ZERO
    for y in sorted(years):
        result=calculate(y,projects,fees,[e for e in annuals if e.payload["year"]<=y],carry,Decimal(form.rate));carry=result["carry"]
    if c.details.get("negative_hint"):result["warnings"].append("负面清单行业需按实际主营收入核实资格")
    return {**result,"year":form.year,"edition":form.edition,"customer":c.name,"status":"年度复核底稿","policy":FORM_SOURCE}

@router.post("/subsidiary/generate")
def generate(form:Ledger,request:Request,db:DB,u:Actor):
    from fastapi.encoders import jsonable_encoder
    result=report(form,db,u)
    result["generated_at"]=now().isoformat();result["rule_version"]="研发年度核对 1.0"
    snap=SavedBook(customer=form.customer,actor=u.id,period=str(form.year),inputs=form.model_dump(),
                   payload=jsonable_encoder(result,custom_encoder={Decimal:str}))
    db.add(snap);db.flush();record(db,request,u,"ledger.generate",form.customer,{"snapshot":snap.id,**form.model_dump()})
    db.commit();return ok({**snap.payload,"snapshot_id":snap.id})

@router.get("/subsidiary/history")
def book_history(customer:int,db:DB,u:Actor):
    from .workflow import manage_customer
    manage_customer(db,u,customer)
    return ok([{"id":s.id,**s.inputs,"generated_at":s.payload["generated_at"]} for s in db.scalars(select(SavedBook).where(SavedBook.customer==customer).order_by(SavedBook.id.desc()))])

@router.get("/subsidiary")
def export(customer:int,year:int,edition:Literal["2015","2021"],request:Request,db:DB,u:Actor,rate:Literal["100","120","75","50"]="100",filing:bool=False,snapshot:int|None=None):
    form=Ledger(customer=customer,year=year,edition=edition,rate=rate)
    if snapshot:
        from .workflow import manage_customer
        manage_customer(db,u,customer);s=db.get(SavedBook,snapshot)
        if not s or s.inputs!=form.model_dump():fail(404,"没有该版本的年度辅助账")
        r=dict(s.payload)
        for p in r["projects"]:
            for k in ("account","hightech","deduction","expense","capitalized","other_allowed","domestic_allowed","foreign_allowed","difference_high","difference_tax"):
                p[k]=Decimal(p[k])
            p["categories"]=[Decimal(v) for v in p["categories"]]
        for detail in r["details"]:detail[6]=Decimal(detail[6])
        r["mapping"]={k:Decimal(v) for k,v in r["mapping"].items()}
    else:r=report(form,db,u)
    if filing and (not all(r["checks"].values()) or r["warnings"]):fail(409,"请先处理全部差异和资格提示，再导出申报核对表")
    projects=r["projects"];ids={p["id"]:p for p in projects}
    summary=[["项目编号","项目名称","会计口径","高企口径","税法归集额","费用化","资本化","其他费用允许额","境内委托允许额","境外委托允许额","高企与会计差异","税法与会计差异"]]+[
        [p[k] for k in ("code","name","account","hightech","deduction","expense","capitalized","other_allowed","domestic_allowed","foreign_allowed","difference_high","difference_tax")] for p in projects]
    summary.append(["合计",""]+[sum((r[i] for r in summary[1:]),ZERO) for i in range(2,len(summary[0]))])
    sheets=[("年度汇总与差异",summary)]
    header=["项目编号","日期","凭证号","科目","摘要","费用类别","凭证金额","特殊事项","依据","费用化/资本化"]
    if edition=="2015":
        for kind in ["自主","委托","合作","集中"]:
            rows=[header+["借方","贷方"]+CATEGORIES]
            for k,*v in r["details"]:
                if ids[k]["category"]!=kind:continue
                debit=v[6] not in {"特殊收入","产品材料冲减","不征税补助"}
                rows.append([ids[k]["code"],*v,v[5] if debit else ZERO,ZERO if debit else v[5],*[v[5] if v[4]==c else ZERO for c in CATEGORIES]])
            sheets.append((kind+"研发辅助账",rows))
    else:
        sheets.append(("项目辅助账",[["编号","名称",*CATEGORIES,"费用化归集","资本化归集"]]+[[p["code"],p["name"],*p["categories"],p["expense"],p["capitalized"]] for p in projects]))
    sheets.append(("凭证索引",[header]+[[ids[k]["code"],*v] for k,*v in r["details"]]))
    sheets.append(("A107012行次核对",[["行次","项目","数值"]]+[[i,LABEL.get(i,"对应费用明细"),r["mapping"][str(i)]] for i in range(1,53)]))
    sheets.append(("勾稽与政策",[["检查","结果"]]+[[k,"通过" if v else "待复核"] for k,v in r["checks"].items()]+[["提示",v] for v in r["warnings"]]+[["表单依据",FORM_SOURCE]]))
    record(db,request,u,"ledger.export",customer,form.model_dump());db.commit()
    return deliver(write_xlsx(sheets),f"{year}-{edition}版研发辅助账.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
