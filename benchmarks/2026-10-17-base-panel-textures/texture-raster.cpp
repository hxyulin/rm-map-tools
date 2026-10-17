// SPDX-License-Identifier: MIT OR Apache-2.0
// Copyright (c) 2026 hxyulin <hxyulin@proton.me>
// Textured diagnostic depth rasterizer, derived from this repository's
// source-separation depth-raster.cpp. Pixel visibility is sampling, not a proof.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <vector>
int main(int argc,char**argv){
 if(argc!=4)return 2;
 FILE*f=fopen(argv[1],"rb");if(!f)return 3;
 int w,h,n;if(fread(&w,4,1,f)!=1||fread(&h,4,1,f)!=1||fread(&n,4,1,f)!=1||w<1||h<1||w>4096||h>4096||n<1)return 4;
 int tw,th;if(fread(&tw,4,1,f)!=1||fread(&th,4,1,f)!=1||tw<1||th<1||tw>4096||th>4096)return 4;std::vector<unsigned char> texture(tw*th*3);if(fread(texture.data(),1,texture.size(),f)!=texture.size())return 4;
 std::vector<float> z(w*h,-INFINITY);std::vector<int32_t> owner(w*h,-1);std::vector<unsigned char> image(w*h*3);
 for(int k=0;k<w*h;k++){image[k*3]=192;image[k*3+1]=208;image[k*3+2]=224;}
 for(int i=0;i<n;i++){
  float p[9],uv[6],shade;int textured;unsigned char c[3];if(fread(p,4,9,f)!=9||fread(c,1,3,f)!=3||fread(uv,4,6,f)!=6||fread(&textured,4,1,f)!=1||fread(&shade,4,1,f)!=1)return 5;
  float a=(p[3]-p[0])*(p[7]-p[1])-(p[4]-p[1])*(p[6]-p[0]);if(std::abs(a)<1e-10)continue;
  int x0=std::max(0,(int)std::floor(std::min({p[0],p[3],p[6]}))),x1=std::min(w-1,(int)std::ceil(std::max({p[0],p[3],p[6]})));
  int y0=std::max(0,(int)std::floor(std::min({p[1],p[4],p[7]}))),y1=std::min(h-1,(int)std::ceil(std::max({p[1],p[4],p[7]})));
  for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
   float u=((p[3]-x-.5f)*(p[7]-y-.5f)-(p[4]-y-.5f)*(p[6]-x-.5f))/a;
   float v=((p[6]-x-.5f)*(p[1]-y-.5f)-(p[7]-y-.5f)*(p[0]-x-.5f))/a,t=1-u-v;
   if(u<0||v<0||t<0)continue;float d=u*p[2]+v*p[5]+t*p[8];int k=y*w+x;
   if(d>z[k]){z[k]=d;owner[k]=i;if(!textured){for(int j=0;j<3;j++)image[k*3+j]=c[j];}else{float sx=std::clamp((u*uv[0]+v*uv[2]+t*uv[4])*tw-.5f,0.f,float(tw-1));float sy=std::clamp((u*uv[1]+v*uv[3]+t*uv[5])*th-.5f,0.f,float(th-1));int ix=int(sx),iy=int(sy),jx=std::min(ix+1,tw-1),jy=std::min(iy+1,th-1);float ax=sx-ix,ay=sy-iy;for(int j=0;j<3;j++){float value=(1-ay)*((1-ax)*texture[(iy*tw+ix)*3+j]+ax*texture[(iy*tw+jx)*3+j])+ay*((1-ax)*texture[(jy*tw+ix)*3+j]+ax*texture[(jy*tw+jx)*3+j]);image[k*3+j]=static_cast<unsigned char>(std::clamp(value*shade,0.f,255.f));}}}
  }
 }
 fclose(f);f=fopen(argv[2],"wb");if(!f)return 6;fprintf(f,"P6\n%d %d\n255\n",w,h);fwrite(image.data(),1,image.size(),f);fclose(f);
 f=fopen(argv[3],"wb");if(!f)return 7;fwrite(owner.data(),4,owner.size(),f);fclose(f);return 0;
}
