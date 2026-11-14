#!/usr/bin/env python3
"""Generate the integrated-board electrical study, never fabrication outputs.

Architecture: power-switch each internal USB device from its hub port. BP uses
directional translation and open-drain control; BA remains an open analogue boundary.
"""
from pathlib import Path
import csv
import json
import os
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'kicad'))
import schematic as s

s.KSYM = os.environ.get('KICAD10_SYMBOL_DIR', s.KSYM.rstrip('/')) + '/'
s.NAME = 'essensys-integrated-study'
s.OUT = str(HERE)
s.U = lambda name: str(uuid.uuid5(uuid.NAMESPACE_URL, 'essensys/integrated/r0/' + name))
s.ROOT = s.U('root')
R_FP = 'Resistor_SMD:R_0603_1608Metric'
C_FP = 'Capacitor_SMD:C_0603_1608Metric'
records = {}
connections = {}

# Local hub symbol: DS00001692E, section 3.1/3.2, USB2512B 36-pin package.
# NCs 6..9 and 18..21 belong to larger siblings and are not USB2512B ports.
hub_pins = {
  1:('USBDM_DN1','bidirectional'),2:('USBDP_DN1','bidirectional'),
  3:('USBDM_DN2','bidirectional'),4:('USBDP_DN2','bidirectional'),
  5:('VDDA33','power_in'),6:('NC6','no_connect'),7:('NC7','no_connect'),
  8:('NC8','no_connect'),9:('NC9','no_connect'),10:('VDDA33','power_in'),
  11:('TEST','input'),12:('PRTPWR1/BC_EN1','bidirectional'),
  13:('OCS_N1','input'),14:('CRFILT','passive'),15:('VDD33','power_in'),
  16:('PRTPWR2/BC_EN2','bidirectional'),17:('OCS_N2','input'),
  18:('NC18','no_connect'),19:('NC19','no_connect'),20:('NC20','no_connect'),
  21:('NC21','no_connect'),22:('SDA/NON_REM1','bidirectional'),
  23:('VDD33','power_in'),24:('SCL/CFG_SEL0','bidirectional'),
  25:('HS_IND/CFG_SEL1','bidirectional'),26:('RESET_N','input'),
  27:('VBUS_DET','input'),28:('SUSP_IND/NON_REM0','bidirectional'),
  29:('VDDA33','power_in'),30:('USBDM_UP','bidirectional'),
  31:('USBDP_UP','bidirectional'),32:('XTALOUT','output'),33:('XTALIN','input'),
  34:('PLLFILT','passive'),35:('RBIAS','passive'),36:('VDDA33','power_in'),
  37:('EP/GND','power_in'),
}
hub_sym=['symbol',s.S('USB2512B'),['pin_names',['offset','1.016']],['in_bom','yes'],['on_board','yes'],
 ['property',s.S('Reference'),s.S('U'),['at','0','52.07','0'],s.fx()],
 ['property',s.S('Value'),s.S('USB2512B'),['at','0','49.53','0'],s.fx()],
 ['symbol',s.S('USB2512B_0_1'),['rectangle',['start','-33.02','48.26'],['end','33.02','-48.26'],['stroke',['width','0'],['type','default']],['fill',['type','background']]]],
 ['symbol',s.S('USB2512B_1_1')]]
for n,(name,typ) in hub_pins.items():
 if n==37: x,y,a=0,-53.34,90
 elif n<=18: x,y,a=-38.1,43.18-(n-1)*5.08,0
 else: x,y,a=38.1,43.18-(n-19)*5.08,180
 hub_sym[-1].append(['pin',typ,'line',['at',s.f(x),s.f(y),str(a)],['length','5.08'],['name',s.S(name),s.fx()],['number',s.S(str(n)),s.fx()]])
s._libs['Integrated']=['kicad_symbol_lib',['version','20241209'],['generator',s.S('kicad_symbol_editor')],hub_sym]
# TI TXU0204 PW/TSSOP14 pin table (SCES936A section 6).
txu_pins={1:('VCCA','power_in'),2:('A1','input'),3:('A2','input'),4:('A3Y','tri_state'),5:('A4Y','tri_state'),6:('NC','no_connect'),7:('GND','power_in'),8:('OE','input'),9:('NC','no_connect'),10:('B4','input'),11:('B3','input'),12:('B2Y','tri_state'),13:('B1Y','tri_state'),14:('VCCB','power_in')}
txu=['symbol',s.S('TXU0204PW'),['pin_names',['offset','1.016']],['in_bom','yes'],['on_board','yes'],['property',s.S('Reference'),s.S('U'),['at','0','22.86','0'],s.fx()],['property',s.S('Value'),s.S('TXU0204PW'),['at','0','20.32','0'],s.fx()],['symbol',s.S('TXU0204PW_0_1'),['rectangle',['start','-15.24','20.32'],['end','15.24','-20.32'],['stroke',['width','0'],['type','default']],['fill',['type','background']]]],['symbol',s.S('TXU0204PW_1_1')]]
for n,(name,typ) in txu_pins.items():
 x,y,ang=(-20.32,15.24-(n-1)*5.08,0) if n<=7 else (20.32,15.24-(14-n)*5.08,180)
 txu[-1].append(['pin',typ,'line',['at',s.f(x),s.f(y),str(ang)],['length','5.08'],['name',s.S(name),s.fx()],['number',s.S(str(n)),s.fx()]])
s._libs['Integrated'].append(txu)
# Local UK suffix variant: same G1/S2/D3 mapping, primary Diodes datasheet.
fet=s.flat_sym('Transistor_FET','DMG2302U')
fet[1]=s.S('DMG2302UK')
for item in fet:
 if isinstance(item,list) and item[0]=='symbol':item[1]=s.S(item[1][1].replace('DMG2302U','DMG2302UK'))
 if isinstance(item,list) and item[0]=='property' and item[1][1]=='Value':item[2]=s.S('DMG2302UK')
 if isinstance(item,list) and item[0]=='property' and item[1][1]=='Datasheet':item[2]=s.S('https://www.diodes.com/datasheet/download/DMG2302UK.pdf')
s._libs['Integrated'].append(fet)
(HERE/'Integrated.kicad_sym').write_text(s.dump(s._libs['Integrated'])+'\n')


def connect(point, net, angle=0):
    # Pin direction determines an outward stub; power labels stand vertically.
    dx,dy={0:(-5.08,0),180:(5.08,0),90:(0,5.08),270:(0,-5.08)}[angle]
    end=(round(point[0]+dx,3),round(point[1]+dy,3))
    s.wire(point,end)
    s.label(net,*end,angle=90 if angle in (90,270) else 0)
    s.items[-1][3]=s.fx(size=1.016,j=['right' if angle==0 else 'left','bottom'])


def part(lid,ref,value,x,y,nets,fp='',unit=1,angle=0,hide_val=False,note=''):
    pins=s.sym(lid,ref,value,fp,x,y,unit=unit,angle=angle,hide_val=hide_val,
       ref_at=(x-6.35,y-5.08),val_at=(x-6.35,y+5.08),extra={'Status':'STUDY_NOT_FOR_FABRICATION','Note':note})
    done=set()
    for n,p in pins.items():
        net=nets.get(n)
        connections.setdefault(ref,{})[n]=net
        if p in done:continue
        done.add(p)
        if net is None:s.no_connect(*p)
        else:
            a=(s.pinmap[lid][n][2]+angle)%360
            connect(p,net,a)
    records.setdefault(ref,{'reference':ref,'value':value,'symbol':lid,'footprint':fp,'lcsc':'','status':'candidate; verify before layout','note':note})
    return pins


def res(ref,value,x,y,a,b):return part('Device:R',ref,value,x,y,{'1':a,'2':b},R_FP,angle=90)
def cap(ref,value,x,y,net,gnd='GND'):return part('Device:C',ref,value,x,y,{'1':net,'2':gnd},C_FP)
def tp(ref,net,x,y):return part('Connector:TestPoint',ref,net,x,y,{'1':net},'TestPoint:TestPoint_Pad_D1.0mm')
def text(t,x,y,size=1.5):s.text(t,x,y,size)
def decouple(prefix,count,x,y,net,value='100n'):
 for i in range(count):cap(f'{prefix}{i+1}',value,x+(i%5)*25.4,y+(i//5)*22.86,net)

def xtal(ref,x,y,a,b,hz,load):
 part('Device:Crystal_GND24',ref,hz,x,y,{'1':a,'2':'GND','3':b,'4':'GND'},'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm')
 cap('C'+ref+'1',load,x-20.32,y+22.86,a);cap('C'+ref+'2',load,x+20.32,y+22.86,b)

text('ESSENSYS — CARTE INTEGREE — ETUDE ELECTRIQUE R0',15.24,15.24,3)
text('RP2350 nu + FX2 + hub USB — deux ports BP / BA. NON FABRICABLE : interface BA ouverte / BP en etude ; budget USB / PCB / banc non qualifies.',15.24,25.4,1.7)

# USB upstream and three deliberately separate power domains.
text('1 / USB ET ALIMENTATIONS COMMUTEES',20.32,40.64,2)
part('Connector:USB_B_Micro','J_USB','USB vers PC',40.64,60.96,{'1':'VBUS_USB','2':'USB_UP_DM','3':'USB_UP_DP','5':'GND','SH':'GND'},note='USB receptacle footprint / ESD part remain to qualify')
part('Regulator_Linear:AP2112K-3.3','U_HREG','AP2112K-3.3',144.78,60.96,{'1':'VBUS_USB','2':'GND','3':'VBUS_USB','5':'+3V3_HUB'},'Package_TO_SOT_SMD:SOT-23-5')
cap('C_HIN','1u',111.76,91.44,'VBUS_USB');cap('C_HOUT','1u',170.18,91.44,'+3V3_HUB')
for n,dom,y in [(1,'FX',124.46),(2,'RP',182.88)]:
 part('Power_Management:TPS2051CDBV',f'U_SW{n}','TPS2051CDBVR',60.96,y,{'1':f'VBUS_{dom}','2':'GND','3':f'HUB_OC{n}_N','4':f'HUB_PWR{n}','5':'VBUS_USB'},'Package_TO_SOT_SMD:SOT-23-5')
 part('Regulator_Linear:AP2112K-3.3',f'U_{dom}REG','AP2112K-3.3',172.72,y,{'1':f'VBUS_{dom}','2':'GND','3':f'VBUS_{dom}','5':f'+3V3_{dom}'},'Package_TO_SOT_SMD:SOT-23-5')
 cap(f'C_SW{n}','100n',25.4,y+22.86,'VBUS_USB');cap(f'C_{dom}IN','1u',124.46,y+22.86,f'VBUS_{dom}');cap(f'C_{dom}OUT','1u',215.9,y+22.86,f'+3V3_{dom}')
 res(f'R_PW{n}','100k',66.04,y+22.86,f'HUB_PWR{n}','GND')
 res(f'R_OC{n}','10k',92.71,y+40.64,f'HUB_OC{n}_N','+3V3_HUB')
text('Hub seul avant enumeration. PRTPWR commande chaque domaine aval.\nInterrupteurs 0.5 A : protection de defaut, pas un budget USB de 500 mA par voie.\nCibles BP/BA alimentees a part. Aucun +15 V sur ces rails.',20.32,230,1.4)

# USB hub straps from primary datasheet; no EEPROM dependency or false self-power.
text('2 / HUB USB2512B — BUS POWER / 2 PORTS INTERNES',285,40.64,2)
hnets={1:'USB_FX_DM',2:'USB_FX_DP',3:'USB_RP_DM',4:'USB_RP_DP',5:'+3V3_HUB',10:'+3V3_HUB',11:'GND',12:'HUB_PWR1',13:'HUB_OC1_N',14:'HUB_CRFILT',15:'+3V3_HUB',16:'HUB_PWR2',17:'HUB_OC2_N',22:'HUB_NONREM1',23:'+3V3_HUB',24:'HUB_CFG0',25:'HUB_CFG1',26:'HUB_RESET_N',27:'HUB_VBUS_DET',28:'HUB_NONREM0',29:'+3V3_HUB',30:'USB_UP_DM',31:'USB_UP_DP',32:'HUB_XOUT',33:'HUB_XIN',34:'HUB_PLLFILT',35:'HUB_RBIAS',36:'+3V3_HUB',37:'GND'}
part('Integrated:USB2512B','U_HUB','USB2512B-AEZC',365.76,109.22,{str(k):v for k,v in hnets.items()},note='36-pin + exposed pad; exact footprint review pending')
for j,(name,val,a,b) in enumerate([('CFG0','100k','HUB_CFG0','GND'),('CFG1','10k','HUB_CFG1','+3V3_HUB'),('NR0','100k','HUB_NONREM0','GND'),('NR1','10k','HUB_NONREM1','+3V3_HUB'),('RST','10k','HUB_RESET_N','+3V3_HUB'),('BIAS','12k 1%','HUB_RBIAS','GND'),('VB1','100k','VBUS_USB','HUB_VBUS_DET'),('VB2','100k','HUB_VBUS_DET','GND')]):
 res('R_H'+name,val,472.44,55.88+j*20.32,a,b)
cap('C_HRST','1u',309.88,190.5,'HUB_RESET_N')
cap('C_HCR','100n',340.36,190.5,'HUB_CRFILT');cap('C_HPLL','100n',375.92,190.5,'HUB_PLLFILT')
xtal('YH',411.48,220.98,'HUB_XIN','HUB_XOUT','24MHz CL12p','20p candidate')
decouple('C_HD',6,284.48,218.44,'+3V3_HUB');cap('C_HB','1u',284.48,264.16,'+3V3_HUB')
text('CFG_SEL=10 : bus-powered ; NON_REM=10 : deux ports fixes.\nBC_EN1/2=0 au reset (100k). 12k RBIAS 1%.\nCharges quartz / USB ESD / empreinte restent a qualifier.',325.12,274.32,1.4)

# Bare RP2350A, QSPI flash, BOOTSEL and recommended switched core regulator.
text('3 / RP2350A NU — PROGRAMMATEUR (INTERFACES OUVERTES)',548.64,40.64,2)
gpio={0:'RP_BA_PGC',1:'RP_BA_PGD_OUT',2:'RP_BA_PGD_IN',3:'RP_BA_PGD_DIR',4:'RP_BA_OE',5:'RP_BA_VPP_EN',8:'RP_BP_DSCLK',9:'RP_BP_DSI',10:'RP_BP_DSO',11:'RP_BP_BKPT',12:'RP_BP_RESET',13:'RP_BP_ALLPST',14:'RP_BP_OE',15:'RP_BP_RESET_SENSE',26:'RP_ADC_BA_VDD',27:'RP_ADC_BA_VPP',28:'RP_ADC_BP_VREF'}
bygp={0:2,1:3,2:4,3:5,4:7,5:8,6:9,7:10,8:12,9:13,10:14,11:15,12:16,13:17,14:18,15:19,16:27,17:28,18:29,19:31,20:32,21:33,22:34,23:35,24:36,25:37,26:40,27:41,28:42,29:43}
rp={n:'+3V3_RP' for n in [1,11,20,30,38,45,44,49,53,54]}
rp.update({n:'+1V1_RP' for n in [6,23,39,50]});rp.update({21:'RP_XIN',22:'RP_XOUT',24:'RP_SWCLK',25:'RP_SWDIO',26:'RP_RUN',46:'RP_VREG_AVDD',47:'GND',48:'RP_LX',51:'RP_DM_PAD',52:'RP_DP_PAD',55:'QSPI_D3',56:'QSPI_CLK',57:'QSPI_D0',58:'QSPI_D2',59:'QSPI_D1',60:'QSPI_CS_N',61:'GND'})
rp.update({bygp[k]:v for k,v in gpio.items()})
part('MCU_RaspberryPi:RP2350A','U_RP','RP2350A',604.52,111.76,{str(k):v for k,v in rp.items()},'Package_DFN_QFN:QFN-60-1EP_7x7mm_P0.4mm_EP3.4x3.4mm')
part('Memory_Flash:W25Q32JVSS','U_FLASH','W25Q32JVSSIQ',762,63.5,{'1':'QSPI_CS_N','2':'QSPI_D1','3':'QSPI_D2','4':'GND','5':'QSPI_D0','6':'QSPI_CLK','7':'QSPI_D3','8':'+3V3_RP'},'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm')
cap('C_FLASH','100n',802.64,63.5,'+3V3_RP')
res('R_CS','10k',754.38,93.98,'QSPI_CS_N','+3V3_RP');res('R_BOOT','1k',754.38,114.3,'QSPI_CS_N','RP_BOOTSW')
part('Switch:SW_Push','SW_BOOT','BOOTSEL',805.18,114.3,{'1':'RP_BOOTSW','2':'GND'})
res('R_DM','27',568.96,185.42,'USB_RP_DM','RP_DM_PAD');res('R_DP','27',568.96,205.74,'USB_RP_DP','RP_DP_PAD')
res('R_RUN','10k',754.38,139.7,'RP_RUN','+3V3_RP')
part('Switch:SW_Push','SW_RUN','RESET',805.18,139.7,{'1':'RP_RUN','2':'GND'})
res('R_XO','1k',731.52,185.42,'RP_XOUT','RP_XOUT_R')
xtal('YR',777.24,205.74,'RP_XIN','RP_XOUT_R','ABM8-272-T3 12MHz','15p')
res('R_VREG','33',665.48,185.42,'+3V3_RP','RP_VREG_AVDD')
part('Device:L','L_RP','3.3uH AOTA-B201610S3R3-101-T',665.48,208.28,{'1':'RP_LX','2':'+1V1_RP'},angle=90,note='Polarized inductor orientation/layout per RP2350 hardware guide; footprint to verify')
cap('C_RAV','4.7u',640.08,241.3,'RP_VREG_AVDD');cap('C_RVIN','4.7u',675.64,241.3,'+3V3_RP');cap('C_RCORE','4.7u',711.2,241.3,'+1V1_RP')
s.flag(736.6,241.3,1);s.label('+1V1_RP',736.6,241.3)
s.flag(624.84,241.3,2);s.label('RP_VREG_AVDD',624.84,241.3)
decouple('C_RD',10,548.64,264.16,'+3V3_RP');decouple('C_RC',3,701.04,264.16,'+1V1_RP')
for j,net in enumerate(['RP_SWCLK','RP_SWDIO','RP_RUN']):tp('TP_S'+str(j),net,751.84+j*25.4,299.72)
text('BP : translator + NMOS open-drain. BA : frontiere toujours ouverte.\nRP2350A : 6 IOVDD, ADC_AVDD, USB_OTP_VDD, QSPI_IOVDD et VREG_VIN decouples.\nAucun firmware de programmation active pour cette revision.',548.64,327.66,1.4)

# FX2 section, source firmware PB0..7 from sigrok fx2lafw.
text('4 / FX2LP — PB0..7 VERS SIGROK',20.32,254,2)
fnet={n:'+3V3_FX' for n in [6,10,14,18,24,34,39,50]};fnet.update({n:'GND' for n in [4,7,13,17,19,33,35,48,21]});fnet.update({11:'FX_XOUT',12:'FX_XIN',15:'USB_FX_DP',16:'USB_FX_DM',22:'FX_SCL',23:'FX_SDA',49:'FX_RESET_N',51:'+3V3_FX',43:'FX_WU2',8:'GND',9:'GND'});fnet.update({25+i:f'FX_D{i}' for i in range(8)})
part('MCU_Cypress:CY7C68013A-56PVX','U_FX','CY7C68013A-56PVXC',86.36,330.2,{str(k):v for k,v in fnet.items()},'Package_SO:SSOP-56_7.5x18.5mm_P0.635mm')
xtal('YF',193.04,284.48,'FX_XIN','FX_XOUT','24MHz CL12p','20p candidate')
res('R_FSCL','2.2k',193.04,330.2,'FX_SCL','+3V3_FX');res('R_FSDA','2.2k',193.04,353.06,'FX_SDA','+3V3_FX')
res('R_FRST','10k',193.04,375.92,'FX_RESET_N','+3V3_FX');cap('C_FRST','10u',193.04,401.32,'FX_RESET_N')
res('R_FWU','10k',193.04,459.74,'FX_WU2','+3V3_FX')
decouple('C_FD',8,25.4,416.56,'+3V3_FX');cap('C_FB','1u',193.04,439.42,'+3V3_FX')
text('FX2 sans EEPROM : demarrage ROM Cypress, firmware charge par USB.\nConfigurer 8 voies PB0..7 ; aucun GPIO FX2 ne rejoint le bus brut.\nFirmware fx2lafw / identite USB / suspend a qualifier avec le pilote hote.',20.32,474.98,1.4)

# Capture paths are genuinely wired: four dual buffers, shunt TVS, no pull-ups.
text('5 / HUIT ENTREES PROTEGEES — ACQUISITION SEULE',284.48,294.64,2)
for ch in range(1,9):
 y=312.42+(ch-1)*27.94
 source='SCL_BUS' if ch==1 else 'SDA_BUS' if ch==2 else f'CH{ch}_TP'
 res(f'R_IN{ch}','1k',299.72,y,source,f'CH{ch}_PROT')
 res(f'R_PD{ch}','1M',363.22,y,f'CH{ch}_PROT','GND')
 if ch>=3:tp(f'TP_CH{ch}',source,264.16,y)
 unit=1 if ch%2 else 2;nr=(ch+1)//2
 part('74xGxx:74LVC2G17',f'U_BUF{nr}','SN74LVC2G17DBVR',477.52,y,{'1' if unit==1 else '3':f'CH{ch}_PROT','6' if unit==1 else '4':f'FX_D{ch-1}'},'Package_TO_SOT_SMD:SOT-23-6',unit=unit,hide_val=unit==2)
for pair in range(4):
 y=326.39+pair*55.88
 part('Power_Protection:SP0502BAHT',f'D_IN{pair+1}','SP0502BAHTG',411.48,y,{'1':f'CH{2*pair+1}_PROT','2':f'CH{2*pair+2}_PROT','3':'GND'},'Package_TO_SOT_SMD:SOT-23')
 part('74xGxx:74LVC2G17',f'U_BUF{pair+1}','SN74LVC2G17DBVR',299.72+pair*55.88,551.18,{'5':'+3V3_FX','2':'GND'},'Package_TO_SOT_SMD:SOT-23-6',unit=3,hide_val=True)
 cap(f'C_BUF{pair+1}','100n',320.04+pair*55.88,551.18,'+3V3_FX')
text('1k / SP0502 = bande passante a mesurer. Aucune promesse 24 MHz.\nBuffer Ioff : verifier courant de fuite et charge du bus appareil eteint.',284.48,581.66,1.3)

# Two passive bus connectors, and two target pin contracts separated from GPIOs.
text('6 / TRAVERSEE I2C',20.32,497.84,2)
for ref,x in [('J_I2C_IN',50.8),('J_I2C_OUT',172.72)]:
 part('Connector_Generic:Conn_02x02_Odd_Even',ref,ref,x,523.24,{'1':'SDA_BUS','2':'SCL_BUS','3':'GND','4':'+15V_PASS'},note='WR-MPC3 connector footprint to verify')
text('+15V_PASS = J_I2C_IN.4 <-> J_I2C_OUT.4 uniquement.\nAlimentation USB distincte ; 0 V commun.\nValidation sur banc exclusivement.',20.32,568.96,1.4)
# Independent reset observation: the command GPIO cannot report target/external reset.
# SN74LVC1G17 DBV: NC1/A2/GND3/Y4/VCC5, Ioff supports VCC=0.
text('BP / RETOUR RESET REEL VERS GPIO15',20.32,591.82,1.5)
res('R_RSTS','1k',60.96,609.6,'BP_RESET_N','BP_RESET_SENSE_IN')
res('R_RSTPD','1M',60.96,632.46,'BP_RESET_SENSE_IN','GND')
part('74xGxx:74LVC1G17','U_RST','SN74LVC1G17DBVR',160.02,612.14,{'2':'BP_RESET_SENSE_IN','3':'GND','4':'RP_BP_RESET_SENSE','5':'+3V3_RP'},'Package_TO_SOT_SMD:SOT-23-5',note='Independent reset sense, Schmitt input, Ioff at VCC=0; external ESD/brownout qualification pending')
cap('C_RST','100n',213.36,612.14,'+3V3_RP')
text('7 / BP EN BDM — ADAPTATION NUMERIQUE ; BA EN ATTENTE',548.64,347.98,2)
bp={'1':'BP_TCLK_UNUSED','2':'BP_BKPT_N','3':'BP_DSO','4':'BP_DSI','5':'BP_ALLPST','6':'BP_DSCLK','7':'BP_VREF','8':'BP_RESET_N','9':'GND','10':'GND'}
ba={'1':'BA_VPP','2':'BA_VDD_SENSE','3':'GND','4':'BA_PGD','5':'BA_PGC'}
part('Connector_Generic:Conn_02x05_Odd_Even','J_BP','BP / BDM -> J33',604.52,378.46,bp,note='J33 target interface; keyed adapter + FC14P decision pending')
part('Connector_Generic:Conn_01x06','J_BA','BA / ICSP -> adapter',797.56,378.46,ba,note='OPEN boundary: no VPP stage or direct GPIO connection')
part('Integrated:TXU0204PW','U_BPX','TXU0204PWR',604.52,439.42,{'1':'+3V3_RP','2':'RP_BP_DSCLK','3':'RP_BP_DSI','4':'RP_BP_DSO','5':'RP_BP_ALLPST','7':'GND','8':'RP_BP_OE','10':'BP_ALLPST','11':'BP_DSO','12':'BP_DSI_BUF','13':'BP_DSCLK_BUF','14':'BP_VREF'},'Package_SO:TSSOP-14_4.4x5mm_P0.65mm')
cap('C_BPA','100n',558.8,403.86,'+3V3_RP');cap('C_BPB','100n',655.32,403.86,'BP_VREF')
s.flag(655.32,383.54,3);s.label('BP_VREF',655.32,383.54)
res('R_BPCLK','47',690.88,375.92,'BP_DSCLK_BUF','BP_DSCLK');res('R_BPDI','47',690.88,396.24,'BP_DSI_BUF','BP_DSI')
res('R_BPDSO','100k',563.88,474.98,'BP_DSO','GND');res('R_BPALL','100k',627.38,474.98,'BP_ALLPST','GND')
for num,request,target,y in [(1,'RP_BP_BKPT','BP_BKPT_N',424.18),(2,'RP_BP_RESET','BP_RESET_N',472.44)]:
 ip1,ip2,op=(1,2,7) if num==1 else (5,6,3)
 part('74xGxx:74LVC2G08','U_BPAND','SN74LVC2G08DCUR',711.2,y,{str(ip1):request,str(ip2):'RP_BP_OE',str(op):f'BP_GATE{num}'},'Package_SO:VSSOP-8_2.3x2mm_P0.5mm',unit=num,hide_val=num==2)
 part('Integrated:DMG2302UK',f'Q_BP{num}','DMG2302UK',787.4,y,{'1':f'BP_GATE{num}','2':'GND','3':target},'Package_TO_SOT_SMD:SOT-23',note='UK suffix candidate: G1 S2 D3, Rds specified at 2.5V')
 res(f'R_REQ{num}','100k',688.34,y+22.86,request,'GND')
 res(f'R_GATE{num}','100k',746.76,y+22.86,f'BP_GATE{num}','GND')
 res(f'R_BPPU{num}','10k',787.4,y-17.78,target,'BP_VREF')
part('74xGxx:74LVC2G08','U_BPAND','SN74LVC2G08DCUR',690.88,520.7,{'8':'+3V3_RP','4':'GND'},'Package_SO:VSSOP-8_2.3x2mm_P0.5mm',unit=3,hide_val=True)
cap('C_BPAND','100n',723.9,520.7,'+3V3_RP')
# Measurement is protected at VDD=0. Two 20k lower legs give 10k when on:
# VREF->10k->node->20k->GND; node->TMUX->ADC->20k->GND => gain 0.5.
part('Analog_Switch:TMUX1574PW','U_SENSE','TMUX1574PWR',579.12,533.4,{'1':'GND','2':'BP_VREF_DIV','4':'RP_ADC_BP_VREF','8':'GND','15':'GND','16':'+3V3_RP'},'Package_SO:TSSOP-16_4.4x5mm_P0.65mm',note='One channel used; power-off protection <=3.6V. Brownout/ADC settling qualification pending')
res('R_VTOP','10k 1%',642.62,510.54,'BP_VREF','BP_VREF_DIV')
res('R_VBOT','20k 1%',642.62,533.4,'BP_VREF_DIV','GND')
res('R_VADC','20k 1%',642.62,556.26,'RP_ADC_BP_VREF','GND')
cap('C_VADC','10n',533.4,533.4,'RP_ADC_BP_VREF');cap('C_SENSE','100n',533.4,563.88,'+3V3_RP')
for j,(g,net) in enumerate((g,net) for g,net in gpio.items() if g in (0,1,2,3,4,5,26,27)):
 x=693.42+(j%4)*33.02;y=551.18+(j//4)*22.86
 tp('TP_GPIO'+str(g),net,x,y)
for j,(net,ref) in enumerate([('RP_BA_OE','R_BAOE'),('RP_BA_VPP_EN','R_VPPEN'),('RP_BP_OE','R_BPOE')]):res(ref,'100k',548.64+j*66.04,591.82,net,'GND')
text('BP: OE=0 desactive TXU + NMOS ; GPIO BKPT/RESET haut = demande assertion bas sur cible.\nVREF alimente cote B du TXU et diviseur ; aucune alimentation pod injectee.\nBA OUVERTE : aucune source VPP. MCLR bas / decharge VPP / VDD a concevoir et qualifier.\nADC BP: gain nominal 0.5, TMUX protection hors tension. Mesures/brownout/ESD a qualifier.',548.64,615.95,1.4)

sch=['kicad_sch',['version','20250114'],['generator',s.S('eeschema')],['uuid',s.ROOT],['paper',s.S('User'),'841','650'],
 ['title_block',['title',s.S('Carte integree RP2350 + FX2 — ETUDE R0 NON FABRICABLE')],['date',s.S('2026-11-14')],['rev',s.S('R0-STUDY')],['comment','1',s.S('Refs #10 — BP en etude / BA ouverte ; aucun PCB ni Gerber')]],
 ['lib_symbols']+s.libsyms]+s.items+[['sheet_instances',['path',s.S('/'),['page',s.S('1')]]],['embedded_fonts','no']]
(HERE/(s.NAME+'.kicad_sch')).write_text(s.dump(sch)+'\n')
(HERE/(s.NAME+'.kicad_pro')).write_text(json.dumps({'meta':{'filename':s.NAME+'.kicad_pro','version':3},'schematic':{},'sheets':[[s.ROOT,'Integrated study']],'text_variables':{}},indent=2)+'\n')
(HERE/'expected-netlist.json').write_text(json.dumps(connections,indent=2,sort_keys=True)+'\n')
(HERE/'gpio-contract.json').write_text(json.dumps({'schema':'essensys.integrated.gpio.v1','revision':'R0-unqualified','hardware_qualified':False,'interfaces_connected':False,'bp_digital_connected':True,'ba_interface_connected':False,'gpio':{v.removeprefix('RP_'):k for k,v in gpio.items()},'active_high_enables':['BA_OE','BA_VPP_EN','BP_OE'],'open_drain_required':['BP_BKPT','BP_RESET'],'active_high_requests':['BP_BKPT','BP_RESET'],'adc_frontend_implemented':False,'bp_vref_adc':{'implemented':True,'gain_nominal':0.5,'input_ohms_nominal':20000,'settle_ms_min':2,'power_off_switch':'TMUX1574','qualified':False}},indent=2)+'\n')
with (HERE/'bom-candidates.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(next(iter(records.values()))));writer.writeheader();writer.writerows(records.values())
libs=sorted({r['symbol'].split(':')[0] for r in records.values()}|{'power'})
rows=[]
for name in libs:
 uri='${KIPRJMOD}/Integrated.kicad_sym' if name=='Integrated' else '${KICAD10_SYMBOL_DIR}/'+name+'.kicad_sym'
 rows.append(f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))')
(HERE/'sym-lib-table').write_text('(sym_lib_table\n  (version 7)\n'+'\n'.join(rows)+'\n)\n')
fplibs=sorted({r['footprint'].split(':')[0] for r in records.values() if r['footprint']})
(HERE/'fp-lib-table').write_text('(fp_lib_table\n  (version 7)\n'+'\n'.join(f'  (lib (name "{name}")(type "KiCad")(uri "${{KICAD10_FOOTPRINT_DIR}}/{name}.pretty")(options "")(descr ""))' for name in fplibs)+'\n)\n')
print(f'Generated electrical study: {len(records)} components; BP digital study / BA boundary OPEN; no PCB/fabrication files.')
