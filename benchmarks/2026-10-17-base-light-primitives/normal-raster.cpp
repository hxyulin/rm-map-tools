// SPDX-License-Identifier: MIT OR Apache-2.0
// Copyright (c) 2026 hxyulin <hxyulin@proton.me>
// Diffuse-only diagnostic with interpolated caller normals, derived from the
// repository visibility rasterizer. Not the runtime PBR renderer or an occlusion proof.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <vector>
int main(int argc,char**argv){
 if(argc!=4)return 2;
 FILE*f=fopen(argv[1],"rb");if(!f)return 3;
 int w,h,n;if(fread(&w,4,1,f)!=1||fread(&h,4,1,f)!=1||fread(&n,4,1,f)!=1||w<1||h<1||w>4096||h>4096||n<1)return 4;
 float light[3];if(fread(light,4,3,f)!=3)return 8;
 std::vector<float> z(w*h,-INFINITY);std::vector<int32_t> owner(w*h,-1);std::vector<unsigned char> image(w*h*3);
 for(int k=0;k<w*h;k++){image[k*3]=192;image[k*3+1]=208;image[k*3+2]=224;}
 for(int i=0;i<n;i++){
  float p[9],normal[9];unsigned char c[3];if(fread(p,4,9,f)!=9||fread(normal,4,9,f)!=9||fread(c,1,3,f)!=3)return 5;
  float a=(p[3]-p[0])*(p[7]-p[1])-(p[4]-p[1])*(p[6]-p[0]);if(std::abs(a)<1e-10)continue;
  int x0=std::max(0,(int)std::floor(std::min({p[0],p[3],p[6]}))),x1=std::min(w-1,(int)std::ceil(std::max({p[0],p[3],p[6]})));
  int y0=std::max(0,(int)std::floor(std::min({p[1],p[4],p[7]}))),y1=std::min(h-1,(int)std::ceil(std::max({p[1],p[4],p[7]})));
  for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
   float u=((p[3]-x-.5f)*(p[7]-y-.5f)-(p[4]-y-.5f)*(p[6]-x-.5f))/a;
   float v=((p[6]-x-.5f)*(p[1]-y-.5f)-(p[7]-y-.5f)*(p[0]-x-.5f))/a,t=1-u-v;
   if(u<0||v<0||t<0)continue;float d=u*p[2]+v*p[5]+t*p[8];int k=y*w+x;
   if(d>z[k]){z[k]=d;owner[k]=i;float norm[3],length=0,dot=0;for(int j=0;j<3;j++){norm[j]=u*normal[j]+v*normal[3+j]+t*normal[6+j];length+=norm[j]*norm[j];dot+=norm[j]*light[j];}float shade=.55f+.45f*std::abs(dot)/std::max(std::sqrt(length),1e-20f);for(int j=0;j<3;j++)image[k*3+j]=std::clamp((int)std::round(c[j]*shade),0,255);}
  }
 }
 fclose(f);f=fopen(argv[2],"wb");if(!f)return 6;fprintf(f,"P6\n%d %d\n255\n",w,h);fwrite(image.data(),1,image.size(),f);fclose(f);
 f=fopen(argv[3],"wb");if(!f)return 7;fwrite(owner.data(),4,owner.size(),f);fclose(f);return 0;
}
