# a script to verify the superglue match pair labels

from model.Superglue.dataset import SuperglueDataset
from model.Birdview.dataset import make_images_info
import os
import argparse
from torch.utils.data import DataLoader
import torch
from model.Superglue.matching import Matching
from model.Superglue.train import make_ground_truth_matrix
import cv2
import numpy as np
from model.Superglue.dataset import pts_from_meter_to_pixel, pts_from_pixel_to_meter



parser = argparse.ArgumentParser(description='SuperglueVerify')
parser.add_argument('--dataset_dir', type=str, default='/media/admini/LENOVO/dataset/kitti/lidar_odometry/birdview_dataset/tmp/', help='dataset_dir')
parser.add_argument('--sequence', type=str, default='00', help='sequence')
parser.add_argument('--use_gpu', type=bool, default=True, help='use_gpu')
parser.add_argument('--positive_search_radius', type=float, default=10, help='positive_search_radius')
parser.add_argument('--saved_model_path', type=str,
                    default='/media/admini/lavie/dataset/birdview_dataset/saved_models', help='saved_model_path')
parser.add_argument('--meters_per_pixel', type=float, default=0.2, help='meters_per_pixel')
parser.add_argument('--tolerance_in_pixels', type=float, default=4, help='tolerance_in_pixels')
parser.add_argument('--tolerance_in_meters', type=float, default=1, help='tolerance_in_meters')
args = parser.parse_args()


def verify():
    """
    This function verify if the keypoints in from superpoint+superglue are correctly labelled by ground truth relative pose
    """
    images_dir = os.path.join(args.dataset_dir, args.sequence)
    images_info = make_images_info(
        struct_filename=os.path.join(args.dataset_dir, 'struct_file_' + args.sequence + '.txt'))
    dataset = SuperglueDataset(images_info=images_info, images_dir=images_dir,
                                     positive_search_radius=args.positive_search_radius,
                                     meters_per_pixel=args.meters_per_pixel)
    data_loader = DataLoader(dataset, batch_size=1, shuffle=True)

    saved_model_file = os.path.join(args.saved_model_path, 'superglue-lidar-birdview.pth.tar')

    config = {
        'superpoint': {
            'nms_radius': 4,
            'keypoint_threshold': 0.005,
            'max_keypoints': 200,
        },
        'Superglue': {
            'weights': 'outdoor',
            'sinkhorn_iterations': 100,
            'match_threshold': 0.2,
        }
    }

    model = Matching(config)
    model_checkpoint = torch.load(saved_model_file, map_location=lambda storage, loc: storage)
    model.load_state_dict(model_checkpoint)
    print("Loaded model checkpoints from \'{}\'.".format(saved_model_file))
    device = torch.device('cuda' if torch.cuda.is_available() and args.use_gpu else 'cpu')
    model.to(device)


    torch.set_grad_enabled(False)

    for target, source, T_target_source in data_loader:
        # iteration += 1
        assert(source.shape == target.shape)
        B, C, W, H = source.shape
        target = target.to(device)
        source = source.to(device)
        pred = model({'image0': target, 'image1': source})
        target_kpts = pred['keypoints0'][0].cpu()
        source_kpts = pred['keypoints1'][0].cpu()
        if len(target_kpts) == 0 or len(source_kpts) == 0:
            continue

        # in superglue/numpy/tensor the coordinates are (i,j) which correspond to (v,u) in PIL Image/opencv
        target_kpts_in_meters = target_kpts * args.meters_per_pixel - 50
        source_kpts_in_meters = source_kpts * args.meters_per_pixel - 50
        match_mask_ground_truth = make_ground_truth_matrix(target_kpts_in_meters, source_kpts_in_meters, T_target_source[0],
                                                           args.tolerance_in_meters)
        target_image_raw = target[0][0].cpu().numpy()
        source_image_raw = source[0][0].cpu().numpy()
        target_image_raw = np.stack([target_image_raw]*3, -1) * 30
        source_image_raw = np.stack([source_image_raw]*3, -1) * 30

        cv2.imshow('target_image_raw', target_image_raw)


        # target_kpts = np.round(target_kpts.numpy()).astype(int)

        T_target_source = T_target_source[0].numpy()
        source_kpts = source_kpts.numpy()

        source_kpts_in_meters = pts_from_pixel_to_meter(source_kpts, args.meters_per_pixel)
        print('T_target_source:\n', T_target_source)
        source_kpts_in_meters_in_target_img = [
            (T_target_source[:3,:3] @ np.array([source_kpt[0], source_kpt[1], 0]) + T_target_source[:3,3])[:2]
            for source_kpt in source_kpts_in_meters
        ]
        source_kpts_in_meters_in_target_img = np.array(source_kpts_in_meters_in_target_img)

        source_kpts_in_target_img = pts_from_meter_to_pixel(source_kpts_in_meters_in_target_img, args.meters_per_pixel)

        source_kpts = np.round(source_kpts).astype(int)
        source_kpts_in_target_img = np.round(source_kpts_in_target_img).astype(int)

        target_image_poi = target_image_raw.copy()
        source_image_poi = source_image_raw.copy()
        for (x0, y0), (x1, y1) in zip(source_kpts, source_kpts_in_target_img):
            # c = c.tolist()
            # cv2.line(target_image, (x0, y0), (x0 + 50, y0 + 50),
            #          color=[255,0,0], thickness=1, lineType=cv2.LINE_AA)
            # display line end-points as circles
            cv2.circle(target_image_poi, (x1, y1), 2, (0, 255, 0), 1, lineType=cv2.LINE_AA)
            cv2.circle(source_image_poi, (x0, y0), 2, (255, 0, 0), 1, lineType=cv2.LINE_AA)
            # cv2.circle(out, (x1 + margin + W0, y1), 2, c, -1,
            #            lineType=cv2.LINE_AA)

        cv2.imshow('target_image', target_image_poi)
        cv2.imshow('source_image', source_image_poi)
        cv2.waitKey(0)

    torch.set_grad_enabled(True)
    pass


def visualize_matching():
    """
    This function visualize the feature point matching pipeline
    """
    images_dir = os.path.join(args.dataset_dir, args.sequence)
    images_info = make_images_info(
        struct_filename=os.path.join(args.dataset_dir, 'struct_file_' + args.sequence + '.txt'))
    dataset = SuperglueDataset(images_info=images_info, images_dir=images_dir,
                               positive_search_radius=args.positive_search_radius,
                               meters_per_pixel=args.meters_per_pixel,
                               return_filename=True)
    data_loader = DataLoader(dataset, batch_size=1, shuffle=True)

    saved_model_file = os.path.join(args.saved_model_path, 'superglue-lidar-birdview.pth.tar')

    config = {
        'superpoint': {
            'nms_radius': 4,
            'keypoint_threshold': 0.005,
            'max_keypoints': 200,
        },
        'Superglue': {
            'weights': 'outdoor',
            'sinkhorn_iterations': 100,
            'match_threshold': 0.1,
        }
    }

    model = Matching(config)
    model_checkpoint = torch.load(saved_model_file, map_location=lambda storage, loc: storage)
    model.load_state_dict(model_checkpoint)
    print("Loaded model checkpoints from \'{}\'.".format(saved_model_file))
    device = torch.device('cuda' if torch.cuda.is_available() and args.use_gpu else 'cpu')
    model.to(device)

    torch.set_grad_enabled(False)

    for target, source, T_target_source, target_filename, source_filename in data_loader:
        # iteration += 1
        assert (source.shape == target.shape)
        print(target_filename[0])
        print(source_filename[0])
        B, C, W, H = source.shape
        target = target.to(device)
        source = source.to(device)
        pred = model({'image0': target, 'image1': source})
        target_kpts = pred['keypoints0'][0].cpu()
        source_kpts = pred['keypoints1'][0].cpu()
        if len(target_kpts) == 0 or len(source_kpts) == 0:
            continue

        # in superglue/numpy/tensor the coordinates are (i,j) which correspond to (v,u) in PIL Image/opencv
        target_kpts_in_meters = target_kpts * args.meters_per_pixel - 50
        source_kpts_in_meters = source_kpts * args.meters_per_pixel - 50
        match_mask_ground_truth = make_ground_truth_matrix(target_kpts_in_meters, source_kpts_in_meters,
                                                           T_target_source[0],
                                                           args.tolerance_in_meters)
        target_image_raw = target[0][0].cpu().numpy()
        source_image_raw = source[0][0].cpu().numpy()
        target_image_raw = np.stack([target_image_raw] * 3, -1) * 30
        source_image_raw = np.stack([source_image_raw] * 3, -1) * 30

        cv2.imshow('target_image_raw', target_image_raw)
        cv2.imshow('source_image_raw', source_image_raw)

        # target_kpts = np.round(target_kpts.numpy()).astype(int)

        T_target_source = T_target_source[0].numpy()
        source_kpts = source_kpts.numpy()
        target_kpts = target_kpts.numpy()

        source_kpts_in_meters = pts_from_pixel_to_meter(source_kpts, args.meters_per_pixel)
        print('T_target_source:\n', T_target_source)
        source_kpts_in_meters_in_target_img = [
            (T_target_source[:3, :3] @ np.array([source_kpt[0], source_kpt[1], 0]) + T_target_source[:3, 3])[:2]
            for source_kpt in source_kpts_in_meters
        ]
        source_kpts_in_meters_in_target_img = np.array(source_kpts_in_meters_in_target_img)

        source_kpts_in_target_img = pts_from_meter_to_pixel(source_kpts_in_meters_in_target_img,
                                                            args.meters_per_pixel)

        source_kpts = np.round(source_kpts).astype(int)
        source_kpts_in_target_img = np.round(source_kpts_in_target_img).astype(int)

        target_image_poi = target_image_raw.copy()
        source_image_poi = source_image_raw.copy()
        for (x0, y0), (x1, y1) in zip(source_kpts, target_kpts):
            # c = c.tolist()
            # cv2.line(target_image, (x0, y0), (x0 + 50, y0 + 50),
            #          color=[255,0,0], thickness=1, lineType=cv2.LINE_AA)
            # display line end-points as circles
            cv2.circle(target_image_poi, (x1, y1), 4, (0, 255, 0), 1, lineType=cv2.LINE_AA)
            cv2.circle(source_image_poi, (x0, y0), 4, (255, 0, 0), 1, lineType=cv2.LINE_AA)
            # cv2.circle(out, (x1 + margin + W0, y1), 2, c, -1,
            #            lineType=cv2.LINE_AA)

        cv2.imshow('target_image_poi', target_image_poi)
        cv2.imshow('source_image_poi', source_image_poi)

        # Matching visualize
        margin = 10
        match_image = np.ones((H, 2 * W + margin))
        match_image = np.stack([match_image] * 3, -1)

        match_image[:, :W] = target_image_poi
        match_image[:, W + margin:] = source_image_poi

        matches = pred['matches0'][0].cpu().numpy()

        valid = matches > -1
        target_kpts_matched = target_kpts[valid]
        source_kpts_matched = source_kpts[matches[valid]]
        for (x0, y0), (x1, y1) in zip(target_kpts_matched, source_kpts_matched):
            cv2.line(match_image, (x0, y0), (x1 + margin + W, y1),
                     color=[0.9, 0.9, 0], thickness=1, lineType=cv2.LINE_AA)
            # display line end-points as circles
            # cv2.circle(match_image, (x0, y0), 2, (0, 255, 0), -1, lineType=cv2.LINE_AA)
            # cv2.circle(match_image, (x1 + margin + W, y1), 2, (255, 0, 0), -1,
            #            lineType=cv2.LINE_AA)
        cv2.imshow('match_image', match_image)
        cv2.waitKey(0)

    torch.set_grad_enabled(True)
    pass


if __name__ == '__main__':
    # verify()
    visualize_matching()