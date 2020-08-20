
import numpy as np
import torch
from gluenet.superglue import SuperGlue
import os
from gluenet.gluenet_with_dgcnn import DgcnnModel
import open3d as o3d
import matplotlib.pyplot as plt
import h5py
from scipy.spatial.transform import Rotation as R
import json


DATA_DIR = '/media/admini/My_data/0629'
h5_filename = os.path.join(DATA_DIR, "submap_segments_downsampled.h5")
correspondences_filename = os.path.join(DATA_DIR, "correspondences.json")

def load_correspondences(correspondences_filename):
    with open(correspondences_filename) as f:
        correspondences_all = json.load(f)['correspondences']
        correspondences_all = [{
            'submap_pair': correspondence['submap_pair'],
            'segment_pairs': np.array(list(map(int, correspondence['segment_pairs'].split(',')[:-1]))).reshape(-1,
                                                                                                               2).transpose(),
        } for correspondence in correspondences_all]
    return correspondences_all

def make_submap_dict(h5file : h5py.File, submap_id : int):
    submap_name = 'submap_' + str(submap_id)
    submap_dict = {}
    submap_dict['num_segments'] = np.array(h5file[submap_name + '/num_segments'])[0]
    segments = []
    center_submap_xy = torch.Tensor([0., 0.])
    num_points = 0
    translation = np.array([50, 50, 0])
    rotation_matrix = R.from_rotvec((-np.pi / 4 + np.random.ranf() * 2 * np.pi / 4) * np.array([0, 0, 1])).as_matrix()
    for i in range(submap_dict['num_segments']):
        # submap_dict[segment_name] = np.array(h5file[submap_name + '/num_segments'])
        segment_name = submap_name + '/segment_' + str(i)
        segment = np.array(h5file[segment_name]) @ rotation_matrix
        segments.append(segment)
        center_submap_xy += segment.sum(axis=0)[:2]
        num_points += segment.shape[0]
    center_submap_xy /= num_points
    # segments = [np.array(segment - np.hstack([center_submap_xy, 0.])) for segment in segments]
    segment_centers = np.array([segment.mean(axis=0) - np.hstack([center_submap_xy, 0.]) for segment in segments])

    submap_dict['segment_centers'] = torch.Tensor(segment_centers)
    submap_dict['segment_scales'] = torch.Tensor(np.array([np.sqrt(segment.var(axis=0)) for segment in segments]))
    submap_dict['segments'] = [torch.Tensor((segment - segment.mean(axis=0)) / np.sqrt(segment.var(axis=0))) for segment
                               in segments]
    submap_dict['segments_original'] = [(segment - np.hstack([center_submap_xy, 0.])) for segment
                               in segments]
    return submap_dict


def match_pipeline(submap_dict_A : dict, submap_dict_B : dict):
    # h5_filename = os.path.join(DATA_DIR, "submap_segments_downsampled.h5")
    # correspondences_filename = os.path.join(DATA_DIR, "correspondences.json")
    # gluenet_dataset = GlueNetDataset(h5_filename, correspondences_filename, mode='test')

    # train_loader = DataLoader(gluenet_dataset, batch_size=1, shuffle=True)

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    descriptor_dim = 256
    # model = DescripNet(k=10, in_dim=3, emb_dims=[64, 128, 128, 512], out_dim=descriptor_dim) # TODO: debug here
    model = DgcnnModel(k=5, feature_dims=[64, 128, 256], emb_dims=[512, 256], output_classes=descriptor_dim)
    model.load_state_dict(torch.load(os.path.join(DATA_DIR, "model-dgcnn-no-dropout.pth"), map_location=torch.device('cpu')))

    super_glue_config = {
        'descriptor_dim': descriptor_dim,
        'weights': '',
        'keypoint_encoder': [32, 64, 128],
        'GNN_layers': ['self', 'cross'] * 6,
        'sinkhorn_iterations': 150,
        'match_threshold': 0.2,
    }
    superglue = SuperGlue(super_glue_config)
    superglue.load_state_dict(torch.load(os.path.join(DATA_DIR, "superglue-dgcnn-no-dropout.pth"), map_location=dev))

    model.train()
    superglue.train()
    model = model.to(dev)
    superglue = superglue.to(dev)

    meta_info_A = torch.cat([submap_dict_A['segment_centers'], submap_dict_A['segment_scales']], dim=1)
    meta_info_B = torch.cat([submap_dict_B['segment_centers'], submap_dict_B['segment_scales']], dim=1)
    segments_A = submap_dict_A['segments']
    segments_B = submap_dict_B['segments']

    with torch.no_grad():
        # segments_A = [segment.to(dev) for segment in segments_A]
        # segments_B = [segment.to(dev) for segment in segments_B]
        # descriptors_A = torch.Tensor.new_empty(1, 256, len(segments_A), device=dev)
        # descriptors_B = torch.Tensor.new_empty(1, 256, len(segments_B), device=dev)
        descriptors_A = []
        descriptors_B = []
        # for i in range(len(segments_A)):
        #     descriptors_A[0, :, i] = model(segments_A[i], dev)
        # for i in range(len(segments_B)):
        #     descriptors_B.append(model(segment, dev))
        for segment in segments_A:
            # descriptors_A.append(model(segment.to(dev), dev))
            descriptors_A.append(model(segment.reshape(1, -1, 3).to(dev)))
        for segment in segments_B:
            # descriptors_B.append(model(segment.to(dev), dev))
            descriptors_B.append(model(segment.reshape(1, -1, 3).to(dev)))
        descriptors_A = torch.cat(descriptors_A, dim=0).transpose(0, 1).reshape(1, descriptor_dim, -1)
        descriptors_B = torch.cat(descriptors_B, dim=0).transpose(0, 1).reshape(1, descriptor_dim, -1)
        data = {
            'descriptors0': descriptors_A,
            'descriptors1': descriptors_B,
            'keypoints0': meta_info_A.reshape(1,-1,6).to(dev),
            'keypoints1': meta_info_B.reshape(1,-1,6).to(dev),
        }

        match_output = superglue(data)

        return match_output


def visualize_match_result(submap_dict_A, submap_dict_B, match_result, segment_pairs_ground_truth):
    num_segments_A = submap_dict_A['segment_centers'].shape[0]
    num_segments_B = submap_dict_B['segment_centers'].shape[0]
    translation_offset_for_visualize = np.array([0, 0, 30])
    # draw correspondence lines
    points = np.vstack([np.array(submap_dict_A['segment_centers']), np.array(submap_dict_B['segment_centers']) + translation_offset_for_visualize])
    lines = []
    line_labels = []

    pcd_A = o3d.geometry.PointCloud()
    pcd_B = o3d.geometry.PointCloud()
    label = 0
    labels_A = []
    for segment in submap_dict_A['segments_original']:
        labels_A += [label] * segment.shape[0]
        label += 1
        pcd_A.points.extend(o3d.utility.Vector3dVector(np.array(segment)[:, :3]))
    labels_A = np.array(labels_A)

    label_B_offest = num_segments_A
    label = label_B_offest
    labels_B = []
    for segment in submap_dict_B['segments_original']:
        labels_B += [label] * segment.shape[0]
        label += 1
        pcd_B.points.extend(o3d.utility.Vector3dVector(np.array(segment)[:, :3] + translation_offset_for_visualize))
    labels_B = np.array(labels_B)

    matches_A_to_B = np.array(match_result['matches0'].cpu()).reshape(-1)
    for label_A in range(len(matches_A_to_B)):
        label_B = matches_A_to_B[label_A] + label_B_offest

        if label_B >= label_B_offest:
            labels_B[labels_B == label_B] = label_A
            lines.append([label_A, label_B])
            candidate_label_B = segment_pairs_ground_truth[:, np.where(segment_pairs_ground_truth[0]==label_A)[0]][1]
            if (label_B-label_B_offest) in candidate_label_B:
                line_labels.append(True)
            else:
                line_labels.append(False)
        else:
            labels_A[labels_A == label_A] = -1

    max_label = labels_A.max()
    labels_B[labels_B > max_label] = -1

    colors_A = plt.get_cmap("tab20")(labels_A / (max_label if max_label > 0 else 1))
    colors_A[labels_A < 0] = 0
    pcd_A.colors = o3d.utility.Vector3dVector(colors_A[:, :3])

    colors_B = plt.get_cmap("tab20")(labels_B / (max_label if max_label > 0 else 1))
    colors_B[labels_B < 0] = 0
    pcd_B.colors = o3d.utility.Vector3dVector(colors_B[:, :3])

    line_set = o3d.geometry.LineSet(
        points=o3d.utility.Vector3dVector(points),
        lines=o3d.utility.Vector2iVector(lines),
    )

    print("precisions={}".format(np.array(line_labels).mean()))

    color_lines = []
    for line_label in line_labels:
        if line_label==True:
            color_lines.append([0, 1, 0])
        else:
            color_lines.append([1, 0, 0])
    line_set.colors = o3d.utility.Vector3dVector(color_lines)
    o3d.visualization.draw_geometries([pcd_A, pcd_B, line_set])

submap_id_A = 231
submap_id_B = 348

correspondences = load_correspondences(correspondences_filename)
segment_pairs_ground_truth = [correspondence for correspondence in correspondences if correspondence["submap_pair"]==(str(submap_id_A) + ',' + str(submap_id_B))][0]['segment_pairs']

h5_file = h5py.File(h5_filename, 'r')
submap_dict_A = make_submap_dict(h5_file, submap_id_A)
submap_dict_B = make_submap_dict(h5_file, submap_id_B)

match_result = match_pipeline(submap_dict_A, submap_dict_B)
visualize_match_result(submap_dict_A, submap_dict_B, match_result, segment_pairs_ground_truth)



# TODO: RANSAC matching