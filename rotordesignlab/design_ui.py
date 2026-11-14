"""One current design across tasks; Chinese fields with persistent draft state."""
from copy import deepcopy
from io import StringIO
import json
import math
import pandas as pd
import streamlit as st

from . import designs
from .aircraft import SCHEMA, SCHEMA_V2
from .parameter_fields import FIELDS, INTERNAL, ENUM_LABELS, label, help_text, location


def current():return st.session_state['design']


def replace_design(design,identifier=None,version=None):
    st.session_state['design']=deepcopy(design)
    st.session_state['design_id']=identifier;st.session_state['design_version']=version
    st.session_state['saved_fingerprint']=designs.digest(design) if identifier else None
    st.session_state['design_epoch']=st.session_state.get('design_epoch',0)+1
    st.session_state['table_bases']={}
    st.session_state['_reset_consent']=True
    task=design['settings'].get('_active_task','孤立旋翼')
    st.session_state['analysis-task']=task if task in ('孤立旋翼','整机悬停预算','整机配平','通用开环操稳') else '孤立旋翼'


def key_for(path):return 'd:'+str(st.session_state['design_epoch'])+':'+ '/'.join(map(str,path))


def get_at(path):
    data=current()
    for key in path:data=data[key]
    return data


def put_at(path,value,remove=False):
    data=get_at(path[:-1]);key=path[-1]
    if remove:
        if key not in data:return
        del data[key]
    else:
        if key in data and data[key]==value:return
        data[key]=value
    if path[0]!='settings':
        if path[0]=='assets':
            index=int(path[1].split('-')[1]);role=current()['aircraft']['rotors'][index].get('role','main')
            note=('主旋翼' if role=='main' else '尾桨')+' / '+('桨叶几何表' if 'geometry' in path[1] else '翼型气动表')
        else:note=location(path[1:])
        edits=current()['settings'].setdefault('_edits',[])
        if note not in edits:edits.append(note)


def dirty():return designs.digest(current())!=st.session_state.get('saved_fingerprint')


def scalar_change(path,key):put_at(path,st.session_state[key])


def optional_change(path,key,initial):
    remembered=current()['settings'].setdefault('_optional_values',{})
    token='/'.join(map(str,path))
    if st.session_state[key]:put_at(path,deepcopy(remembered.get(token,initial)))
    else:
        remembered[token]=deepcopy(get_at(path));put_at(path,None,remove=True)


def scalar(path,schema):
    name=path[-1];value=get_at(path);key=key_for(path)
    kwargs=dict(key=key,help=help_text(name),on_change=scalar_change,args=(path,key))
    if 'enum' in schema:
        options=schema['enum']
        st.selectbox(label(name),options,index=options.index(value) if value in options else None,
                     format_func=lambda v:ENUM_LABELS.get(v,str(v)),**kwargs)
    elif schema.get('type')=='boolean':
        kwargs.pop('help');st.checkbox(label(name),value=bool(value),**kwargs);st.caption(help_text(name))
    elif schema.get('type') in ('number','integer'):
        integer=schema['type']=='integer'
        st.number_input(label(name),value=(int(value) if integer else float(value)) if value is not None else None,
                        step=1 if integer else None,format='%d' if integer else '%.9g',placeholder='待填写',**kwargs)
    elif schema.get('type')=='string':
        if name in ('description','provenance'):st.text_area(label(name),value=value or '',**kwargs)
        else:st.text_input(label(name),value=value or '',**kwargs)


def clean(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def table_delta(base,state):
    rows=deepcopy(base)
    for i,changes in state.get('edited_rows',{}).items():
        if int(i)<len(rows):rows[int(i)].update({k:clean(v) for k,v in changes.items()})
    rows=[r for i,r in enumerate(rows) if i not in state.get('deleted_rows',[])]
    rows.extend(state.get('added_rows',[]))
    return rows


def edit_table(rows,path,apply,*,columns=None,dynamic=False,disabled=()):
    key=key_for(path);bases=st.session_state.setdefault('table_bases',{})
    if key not in st.session_state or key not in bases:bases[key]=deepcopy(rows)
    base=bases[key]
    def changed():apply(table_delta(base,st.session_state[key]))
    frame=pd.DataFrame(base)
    config=columns or {c:st.column_config.NumberColumn(label(c),help=help_text(c),format='%.9g') for c in frame.columns}
    for col,cfg in config.items():
        if cfg.get('type_config',{}).get('type')=='number':
            if col not in frame:frame[col]=pd.Series(dtype=float)
            else:frame[col]=pd.to_numeric(frame[col],errors='coerce').astype(float)
    out=st.data_editor(frame,hide_index=True,num_rows='dynamic' if dynamic else 'fixed',
                       column_config=config,disabled=list(disabled),key=key,on_change=changed,
                       placeholder='待填写',alt=location(path))
    # Applying the returned table also supports programmatic replay and tests.
    normalized=[{k:clean(v) for k,v in row.items()} for row in out.to_dict('records')]
    if normalized!=rows:apply(normalized)


def column_table(path,data,dynamic=True):
    names=list(data);length=max((len(v) for v in data.values()),default=0)
    rows=[{k:data[k][i] if i<len(data[k]) else None for k in names} for i in range(length)]
    config={k:st.column_config.NumberColumn(label(k),help=help_text(k),format='%.9g') for k in names}
    if 'beta_table' in path and 'cl' in names:config['cl']=st.column_config.NumberColumn('滚转力矩系数 Cl',format='%.9g')
    def apply(values):put_at(path,{k:[r.get(k) for r in values] for k in names})
    edit_table(rows,path,apply,columns=config,dynamic=dynamic)


def array_editor(path,schema):
    data=get_at(path);name=path[-1]
    st.caption(label(name)+'：'+help_text(name))
    if name=='inertia_cg_kg_m2':
        rows=[dict(行=x,x=data[i][0],y=data[i][1],z=data[i][2]) for i,x in enumerate('xyz')]
        config={'行':st.column_config.TextColumn('张量行'),**{x:st.column_config.NumberColumn(f'{x}列 / (kg·m²)',help=help_text(name),format='%.9g') for x in 'xyz'}}
        edit_table(rows,path,lambda v:put_at(path,[[r.get(x) for x in 'xyz'] for r in v]),columns=config,disabled=['行'])
    else:
        vector=len(data)==3 and schema.get('maxItems')==3
        columns=list('xyz') if vector else ['下限','上限']
        rows=[dict(zip(columns,data))]
        config={c:st.column_config.NumberColumn(c,help=help_text(name),format='%.9g') for c in columns}
        edit_table(rows,path,lambda v:put_at(path,[v[0].get(c) for c in columns]),columns=config)


def object_editor(path,schema):
    data=get_at(path);properties=schema.get('properties',{})
    # Column arrays are editable tables. No row is reordered or silently interpolated.
    table_keys=[k for k,v in properties.items() if v.get('type')=='array' and v.get('items',{}).get('type')=='number']
    if table_keys:
        subset={k:data.get(k,[]) for k in table_keys}
        names=list(subset);size=max((len(v) for v in subset.values()),default=0)
        rows=[{k:subset[k][i] if i<len(subset[k]) else None for k in names} for i in range(size)]
        def apply(values):
            for k in names:put_at(path+[k],[r.get(k) for r in values])
        config={k:st.column_config.NumberColumn(label(k),help=help_text(k),format='%.9g') for k in names}
        if path[-1]=='beta_table' and 'cl' in names:config['cl']=st.column_config.NumberColumn('滚转力矩系数 Cl',format='%.9g')
        edit_table(rows,path+['_table'],apply,columns=config,dynamic=True)
    for name,child in properties.items():
        if name in INTERNAL or name in table_keys:continue
        child=SCHEMA_V2['$defs'][child['$ref'].split('/')[-1]] if '$ref' in child else child
        if name not in data:
            if name in schema.get('required',[]):data[name]=None
            else:
                initial=False if child.get('type')=='boolean' else {} if child.get('type')=='object' else ([[None]*3 for _ in range(3)] if name=='inertia_cg_kg_m2' else
                    ([None]*child.get('minItems',2) if child.get('type')=='array' else None))
                opt=key_for(path+[name,'enable'])
                st.checkbox('填写'+label(name),value=False,key=opt,on_change=optional_change,args=(path+[name],opt,initial))
                st.caption(help_text(name))
                continue
        elif name not in schema.get('required',[]) and name not in ('description','provenance'):
            opt=key_for(path+[name,'enable'])
            st.checkbox('填写'+label(name),value=True,key=opt,on_change=optional_change,args=(path+[name],opt,None))
        if data.get(name) is None and child.get('type')=='object':data[name]={}
        if child.get('type')=='object':
            with st.expander(label(name),expanded=name=='defaults'):
                st.caption(help_text(name));object_editor(path+[name],child)
        elif child.get('type')=='array':
            if data[name] is None:st.caption(label(name)+'：待补充');continue
            array_editor(path+[name],child)
        else:scalar(path+[name],child)


def csv_editor(rotor,index,key):
    name=rotor[key];data=pd.read_csv(StringIO(current()['assets'][name]))
    title='桨叶几何' if key=='geometry_csv' else '翼型极曲线'
    with st.expander(title+' CSV 载入与模板'):
        st.caption('保留原有CSV载入功能；UTF-8编码，列顺序按下载模板填写。支持中文模板列名，也兼容原英文列名。')
        st.download_button('下载'+title+' CSV 模板',data.rename(columns={k:label(k) for k in data.columns}).to_csv(index=False).encode('utf-8-sig'),
                           title+'.csv',key=key_for(['csv-download',name]))
        upload=st.file_uploader('载入'+title+' CSV',type='csv',key=key_for(['csv-upload',name]))
        if st.button('应用'+title+' CSV',key=key_for(['csv-apply',name]),disabled=upload is None):
            try:
                text=upload.getvalue().decode('utf-8-sig')
                incoming=pd.read_csv(StringIO(text)).rename(columns={label(k):k for k in data.columns})
                if list(incoming.columns)!=list(data.columns):raise ValueError('CSV列名或顺序与模板不一致。')
                content=incoming.to_csv(index=False);candidate=deepcopy(current());candidate['assets'][name]=content
                problems=designs.issues(candidate)
                if problems:raise ValueError('\n'.join(problems))
                put_at(['assets',name],content)
                st.session_state['design_epoch']+=1;st.session_state['table_bases']={};st.rerun()
            except (ValueError,UnicodeError) as e:st.error(str(e))
    path=['assets',name]
    def apply(rows):put_at(path,pd.DataFrame(rows,columns=data.columns).to_csv(index=False))
    edit_table(data.to_dict('records'),path,apply,dynamic=True)


def airfoil_editor(rotor,index):
    if 'polar_csv' in rotor:
        st.caption('单张极曲线；攻角为°，CL/CD为无量纲。更改数据后请填写旋翼参数来源。')
        csv_editor(rotor,index,'polar_csv');return
    name=rotor['polar_json'];grid=json.loads(current()['assets'][name]);sections=grid['sections']
    section=st.selectbox('展向翼型站',range(len(sections)),format_func=lambda i:f"r/R = {sections[i]['r_over_R']:g}",key=key_for(['airfoil',index,'span']),help='选择该半径比处的翼型数据；中间展向位置由现有求解器插值。')
    slices=sections[section].get('reynolds_slices',[sections[section]])
    selected=st.selectbox('Re 数据层',range(len(slices)),format_func=lambda i:f"Re = {slices[i]['reynolds']:g}" if 'reynolds' in slices[i] else '不区分 Re',key=key_for(['airfoil',index,'re']),help='Re为以当地弦长和相对速度计算的雷诺数。表内按log(Re)插值；未分层的原表不具备Re修正。')
    coefficient=st.selectbox('气动系数',['cl','cd'],format_func=lambda v:label(v),key=key_for(['airfoil',index,'coefficient']),help='CL是升力系数，CD是阻力系数，均无量纲；各列对应Mach数，各行对应攻角。')
    table=slices[selected][coefficient]
    st.caption('保留原展向、Re、Mach网格及高攻角分段；当前可编辑系数值。新增维度、数据表导入在表格导入版本接入。')
    columns=['alpha_deg']+[f'Ma={m:g}' for m in table['mach']]
    rows=[dict(zip(columns,[a]+v)) for a,v in zip(table['alpha_deg'],table['values'])]
    def apply(rows):
        table['values']=[[r.get(k) for k in columns[1:]] for r in rows]
        put_at(['assets',name],json.dumps(grid,ensure_ascii=False,allow_nan=False))
    config={k:st.column_config.NumberColumn(label(k) if k=='alpha_deg' else k,help=help_text('alpha_deg' if k=='alpha_deg' else coefficient),format='%.9g') for k in columns}
    edit_table(rows,['airfoil',index,section,selected,coefficient],apply,columns=config,disabled=['alpha_deg'])
    if 'outer_alpha' in table:
        outer=table['outer_alpha'];st.caption('高攻角独立分支（原UT口径，不随主表重新插值）')
        rows=[dict(alpha_deg=a,value=v) for a,v in zip(outer['alpha_deg'],outer['values'])]
        def outer_apply(rows):
            outer['values']=[r.get('value') for r in rows]
            put_at(['assets',name],json.dumps(grid,ensure_ascii=False,allow_nan=False))
        edit_table(rows,['airfoil',index,section,selected,coefficient,'outer'],outer_apply,
                   columns={'alpha_deg':st.column_config.NumberColumn('攻角 / °'),'value':st.column_config.NumberColumn(label(coefficient),format='%.9g')},disabled=['alpha_deg'])


def details():
    a=current()['aircraft'];props=(SCHEMA_V2 if a['schema_version']==2 else SCHEMA)['properties']
    with st.expander('详细设置：机型、旋翼、气动与动力',expanded=False):
        st.info('机体系：x向前、y向右、z向下。位置共用同一原点；重心和部件位置均填绝对坐标，程序计算相对力臂。单位向量不自动归一化，以便检查填写错误。')
        groups=['基本信息','质量、重心与惯量','主旋翼','尾桨','悬停下载','动力与传动','配平姿态限制','机身','平尾与垂尾']
        group=st.selectbox('参数分组',groups,key='parameter-group',help='本次计算的总距、转速与来流在计算页直接填写；这里设置方案的几何、安装、气动、质量和限制。')
        if group=='基本信息':
            st.caption('方案名称在上方“方案管理”中修改。')
            object_editor(['aircraft'],dict(properties={k:props[k] for k in ('description','provenance')}))
        elif group=='质量、重心与惯量':object_editor(['aircraft','mass_properties'],props['mass_properties'])
        elif group in ('主旋翼','尾桨'):
            indexes=[i for i,r in enumerate(a['rotors']) if r.get('role','main')==('main' if group=='主旋翼' else 'tail')]
            if not indexes:st.info('此模板未配置尾桨。整机任务请从完整直升机模板新建方案。');return
            i=indexes[0];rotor=a['rotors'][i];schema=props['rotors']['items']
            page=st.radio('旋翼设置内容',['参数与操纵','桨叶几何表','翼型气动表'],horizontal=True,key='rotor-page',help='参数与操纵包含桨叶数、半径、安装、参考工况和限位；另两页可直接编辑数值表。')
            if page=='参数与操纵':object_editor(['aircraft','rotors',i],schema)
            elif page=='桨叶几何表':
                st.caption('r/R递增到1；弦长是实际米数；扭转相对总距参考站归零后使用。表格可以直接增加/删除径向站。')
                csv_editor(rotor,i,'geometry_csv')
            else:airfoil_editor(rotor,i)
        else:
            path={'悬停下载':['hover'],'动力与传动':['powerplant'],'配平姿态限制':['trim'],
                  '机身':['trim','fuselage'],'平尾与垂尾':['trim','surfaces']}[group]
            if path[0] not in a:st.info('此模板未配置整机参数；请从完整直升机模板新建。');return
            schema=props[path[0]]
            if len(path)>1:schema=schema['properties'][path[1]]
            if group=='配平姿态限制':schema=dict(schema,properties={k:v for k,v in schema['properties'].items() if k not in ('fuselage','surfaces')})
            if group=='平尾与垂尾':
                surfaces=a['trim']['surfaces']
                if not surfaces:st.info('当前方案没有尾翼。');return
                i=st.selectbox('选择尾翼',range(len(surfaces)),format_func=lambda j:{'horizontal_tail':'平尾','vertical_tail':'垂尾'}.get(surfaces[j]['id'],f'气动面{j+1}'))
                object_editor(['aircraft',*path,i],schema['items'])
            else:object_editor(['aircraft',*path],schema)


def manager():
    if 'design' not in st.session_state:replace_design(designs.from_template(next(iter(designs.TEMPLATES))))
    if st.session_state.pop('_reset_consent',False):st.session_state['replace-consent']=False
    st.subheader('当前方案：'+current()['aircraft']['name'])
    if '_design_notice' in st.session_state:st.success(st.session_state.pop('_design_notice'))
    status=st.empty()
    with st.expander('方案管理：新建、保存、重开与导入'):
        st.caption('修改名称即可重命名。保存到本机方案库；另存会保留原方案。下载的.rdl包可在另一目录/电脑导入，用户无需编辑内部文件。')
        scalar(['aircraft','name'],{'type':'string'})
        a,b=st.columns(2)
        template=a.selectbox('新建所用模板',list(designs.TEMPLATES),key='new-template',help='模板提供一套完整初始参数。合成模板用于操作与数值检查，公开模型含来源及工程估计说明。')
        saved=designs.saved_designs();names=dict(saved)
        identifier=b.selectbox('已保存方案',[i for i,n in saved],format_func=lambda i:names[i]+' · '+i[:6],index=0 if saved else None,help='选择本机保存的方案后点击重新打开；名称后短编号用于区分重名方案。')
        consent=st.checkbox('确认替换当前草稿（新建、重开、导入或恢复模板时使用）',key='replace-consent')
        a,b,c,d=st.columns(4)
        if a.button('从模板新建'):
            if not dirty() or consent:replace_design(designs.from_template(template));st.rerun()
            else:st.warning('当前有未保存修改，请先保存，或勾选替换当前草稿。')
        if b.button('保存方案',type='primary'):
            try:
                i,v=designs.save_design(current(),st.session_state.get('design_id'),st.session_state.get('design_version'))
                st.session_state.update(design_id=i,design_version=v,saved_fingerprint=designs.digest(current()))
                st.session_state['_design_notice']='方案已保存到本机。';st.rerun()
            except (ValueError,OSError) as e:st.error(str(e))
        if c.button('另存为新方案'):
            try:
                i,v=designs.save_design(current());st.session_state.update(design_id=i,design_version=v,saved_fingerprint=designs.digest(current()))
                st.session_state['_design_notice']='已另存，原方案保持不变。';st.rerun()
            except (ValueError,OSError) as e:st.error(str(e))
        if d.button('重新打开',disabled=not saved):
            if not dirty() or consent:
                try:
                    design,v=designs.load_design(identifier);replace_design(design,identifier,v);st.rerun()
                except (ValueError,OSError) as e:st.error(str(e))
            else:st.warning('请先保存修改，或确认替换当前草稿。')
        upload=st.file_uploader('导入已导出的方案包',type='rdl')
        if st.button('应用导入方案',disabled=upload is None):
            if not dirty() or consent:
                try:replace_design(designs.unpack(upload.getvalue()));st.rerun()
                except ValueError as e:st.error(str(e))
            else:st.warning('请先保存修改，或确认替换当前草稿。')
        if st.button('恢复原模板参数'):
            if current()['template'] not in designs.TEMPLATES:st.warning('此导入方案没有对应的本机模板，请从模板新建。')
            elif consent:replace_design(designs.from_template(current()['template']));st.rerun()
            else:st.warning('恢复会替换机型、气动表和各任务工况，请先保存或勾选替换当前草稿。')
        try:payload=designs.pack(current())
        except ValueError:st.caption('请修正参数后下载方案包。')
        else:st.download_button('下载当前方案包',payload,'rotordesignlab-design.rdl',key='download-design')
    if dirty():status.warning('当前草稿尚未保存。切换分析任务会保留修改；关闭或刷新网页前请保存方案。')
    else:status.success('当前方案已保存。')
    return current()
