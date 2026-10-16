// SPDX-License-Identifier: MIT OR Apache-2.0
// Copyright (c) 2026 hxyulin <hxyulin@proton.me>
#include <cstdio>
#include <vector>
#include <cmath>
#include <algorithm>
int main(int argc,char**argv){FILE*f=fopen(argv[1],"rb");int w,h,n;fread(&w,4,1,f);fread(&h,4,1,f);fread(&n,4,1,f);std::vector<float> z(w*h,-INFINITY);std::vector<unsigned char> im(w*h*3,245);for(int i=0;i<n;i++){float p[9];unsigned char c[3];fread(p,4,9,f);fread(c,1,3,f);float a=(p[3]-p[0])*(p[7]-p[1])-(p[4]-p[1])*(p[6]-p[0]);if(std::abs(a)<1e-10)continue;int x0=std::max(0,(int)std::floor(std::min({p[0],p[3],p[6]}))),x1=std::min(w-1,(int)std::ceil(std::max({p[0],p[3],p[6]})));int y0=std::max(0,(int)std::floor(std::min({p[1],p[4],p[7]}))),y1=std::min(h-1,(int)std::ceil(std::max({p[1],p[4],p[7]})));for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){float u=((p[3]-x-.5f)*(p[7]-y-.5f)-(p[4]-y-.5f)*(p[6]-x-.5f))/a;float v=((p[6]-x-.5f)*(p[1]-y-.5f)-(p[7]-y-.5f)*(p[0]-x-.5f))/a;float t=1-u-v;if(u<0||v<0||t<0)continue;float d=u*p[2]+v*p[5]+t*p[8];int k=y*w+x;if(d>z[k]){z[k]=d;for(int j=0;j<3;j++)im[k*3+j]=c[j];}}}fclose(f);f=fopen(argv[2],"wb");fprintf(f,"P6\n%d %d\n255\n",w,h);fwrite(im.data(),1,im.size(),f);fclose(f);}
