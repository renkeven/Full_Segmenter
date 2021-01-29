import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1' 
import tensorflow as tf
import context
import numpy as np
from segmenter import tile_images, outputs
import sys
from matplotlib import pyplot as plt
from PIL import Image

import argparse
parser = argparse.ArgumentParser()

parser.add_argument("-i", "--imfile", help="path to image file")
parser.add_argument("-t", "--maskfile", default=None, help="path to mask file") #t is for 'truth' here
parser.add_argument("-m", "--modelfile", default="./models/model_unet_2_retiled.hdf5", help="path to model file")
parser.add_argument("-o", "--outdir", help="output directory")
parser.add_argument("-w", "--weights", default="1,1", help="output weights for the network")

args = parser.parse_args()

gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
  try:
    for gpu in gpus:
      tf.config.experimental.set_memory_growth(gpu, True)
  except RuntimeError as e:
    print(e)

brightness_const = 16
out_dim = np.array([256,256,1])

imfile = args.imfile
outdir = args.outdir
maskpath = args.maskfile
modelpath = args.modelfile
weightarr = np.fromstring(args.weights,sep=',').astype(np.float64)

#INPUT LARGE IMAGE
print(f'starting with image: {imfile}')
print(f'model: {modelpath}')
print(f'save directory: {outdir}')
model = tf.keras.models.load_model(modelpath
                                   ,custom_objects={'<lambda>': lambda y_true, y_pred: y_pred})


#name for output file, remove dir path, remove extension
strbase = ''.join(imfile.split('/')[-1].split('\\')[-1].split('.')[:-1])
big_image = tile_images.read_image(imfile)
if maskpath is not None:
  if 'png' in maskpath:
    big_mask = tile_images.read_image(maskpath)
    big_mask = big_mask == 0
    big_mask = big_mask.astype('uint8')
  else:
    big_mask = np.loadtxt(maskpath,dtype=int,delimiter=' ',comments='#',ndmin=2)
    big_mask = big_mask == 1
    big_mask = big_mask.astype('uint8')

  print(f'big mask shape {big_mask.shape}')

in_dim = np.array(big_image.shape)
in_dim = in_dim - in_dim%out_dim

print(f'cropping image from {big_image.shape} to {in_dim} to fit tiling')

big_image = big_image[:in_dim[0],:in_dim[1],...]
if maskpath is not None:
  big_mask = big_mask[:in_dim[0],:in_dim[1],...]

n_tiles = (in_dim[0]*in_dim[1])//(out_dim[0]*out_dim[1])

#TILE TO (N,256,256,C)

tilebuf = np.zeros((n_tiles,out_dim[0],out_dim[1],3),dtype=np.uint8)
print(f'tiling to {tilebuf.shape}')

tilebuf[...,0] = tile_images.blockshaped(big_image[...,0],out_dim[0],out_dim[1])
tilebuf[...,1] = tile_images.blockshaped(big_image[...,1],out_dim[0],out_dim[1])
tilebuf[...,2] = tile_images.blockshaped(big_image[...,2],out_dim[0],out_dim[1])

#MODEL.PREDICT FOR EACH TILE
print(f'performing image segmentation for {n_tiles} tiles')

pred_mask = np.zeros([n_tiles,256,256])

for i,tile in enumerate(tilebuf):
    img = tile.astype(float) / 255.
    pred_mask[i,...],_ = outputs.create_mask(model,img,weights=weightarr)

pred_mask = outputs.to_colors(pred_mask)
if maskpath is not None:
  big_mask = outputs.to_colors(big_mask)

out_image = np.zeros(big_image.shape)

#RE-CONSTRUCT LARGE IMAGE FROM TILES
print(f're-stitching...')
out_image[...,0] = tile_images.unblockshaped(pred_mask[...,0],in_dim[0],in_dim[1])
out_image[...,1] = tile_images.unblockshaped(pred_mask[...,1],in_dim[0],in_dim[1])
out_image[...,2] = tile_images.unblockshaped(pred_mask[...,2],in_dim[0],in_dim[1])

out_image = (out_image*255).astype(np.uint8)

fig = plt.figure(figsize=(8,6))
ax = fig.add_subplot(221)
ax.imshow(tilebuf[0,...],interpolation='none')
ax = fig.add_subplot(222,sharex=ax,sharey=ax)
ax.imshow(big_image[:256,:256,:],interpolation='none')
ax = fig.add_subplot(223,sharex=ax,sharey=ax)
ax.imshow((pred_mask[0,...]*255).astype(np.uint8),interpolation='none')
ax = fig.add_subplot(224,sharex=ax,sharey=ax)
ax.imshow(out_image[:256,:256,:],interpolation='none')
#plt.show()
#quit()

outname = f'{outdir}/mask_{strbase}.png'
print(f'saving to {outname}')
im = Image.fromarray(out_image)
im.save(outname)

print(big_image.shape)
print(out_image.shape)
if maskpath is not None:
  print(big_mask.shape)

if maskpath is not None:
  fig = plt.figure(figsize=(8,5))
  ax = fig.add_subplot(131)
  ax.imshow(big_image,interpolation='none')
  ax = fig.add_subplot(132,sharex=ax,sharey=ax)
  ax.imshow(out_image,interpolation='none')
  ax = fig.add_subplot(133,sharex=ax,sharey=ax)
  ax.imshow(big_mask,interpolation='none')
  plt.show()

  #print error matrix
  true_pos = np.sum(np.logical_and(out_image == 1, big_mask == 1))
  fals_pos = np.sum(np.logical_and(out_image == 1 & big_mask == 0))
  true_neg = np.sum(np.logical_and(out_image == 0 & big_mask == 0))
  fals_neg = np.sum(np.logical_and(out_image == 0 & big_mask == 1))

  print(f'accuracy = {(true_pos + true_neg)/(true_pos + true_neg + fals_neg + fals_pos)}')
  print(f'precision = {true_pos/(true_pos+fals_pos)}')
  print(f'recall = {true_pos/(true_pos+fals_neg)}')

else:
  fig = plt.figure(figsize=(8,5))
  ax = fig.add_subplot(121)
  ax.imshow(big_image,interpolation='none')
  ax = fig.add_subplot(122,sharex=ax,sharey=ax)
  ax.imshow(out_image,interpolation='none')
  plt.show()