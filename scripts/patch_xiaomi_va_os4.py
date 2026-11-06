#!/usr/bin/env python3
"""Recognize OS4's page-size-dependent RefBase pointer upper bounds."""
import argparse,hashlib,json,struct
from pathlib import Path
from patch_xiaomi_va import guards as old_guards

def patch(data):
 if data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=183:return data,[]
 sites=[at for at,va in old_guards(data)]
 shoff=struct.unpack_from('<Q',data,40)[0];entsize,count=struct.unpack_from('<HH',data,58)
 for i in range(count):
  _,_,flags,addr,off,size,*_=struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*entsize)
  if not flags&4:continue
  candidates=[];cursor=off
  while True:
   found=data.find(struct.pack('<I',0xb2409be8),cursor,off+size-28)
   if found<0:break
   cursor=found+4
   if (found-off)%4==0:candidates.append(found)
  for at in candidates:
   word=struct.unpack_from('<I',data,at)[0]
   if word!=0xb2409be8:continue
   following=[struct.unpack_from('<I',data,at+j)[0] for j in range(0,32,4)]
   # Compiler can schedule the page-size cmp before or after the first MOV.
   if following[1]==0x7140101f and following[2]==0xb240bbe9:
    second=at+8;select_at=at+12;call_at=at-4
   elif at>=off+8 and struct.unpack_from('<I',data,at-4)[0]==0x7140101f and following[1]==0xb240bbe9:
    second=at+4;select_at=at+8;call_at=at-8
   else:continue
   if struct.unpack_from('<I',data,call_at)[0]&0xfc000000!=0x94000000:continue
   select=struct.unpack_from('<I',data,select_at)[0]
   if select&~31!=0x9a880120:continue
   dest=select&31
   for cmp_at in range(select_at+4,min(select_at+20,off+size),4):
    compare=struct.unpack_from('<I',data,cmp_at)[0]
    if compare&0xffe0fc1f==0xeb00001f and (compare>>16)&31==dest:
     sites.extend([at,second]);break
    # Only allow NOP, ADR/ADRP or MOV to unrelated destination while scheduling cmp.
    if compare==0xd503201f:continue
    if compare&31==dest:break
    if (compare&0x9f000000) in (0x10000000,0x90000000) or (compare&0xffe0ffe0)==0xaa0003e0:continue
    break
 updated=bytearray(data)
 for at in sites:
  reg=struct.unpack_from('<I',data,at)[0]&31
  struct.pack_into('<I',updated,at,0xb240dfe0|reg)
 return bytes(updated),sorted(set(sites))
