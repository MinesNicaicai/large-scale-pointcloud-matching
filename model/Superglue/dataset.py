import os

import numpy as np
import torchvision.transforms as transforms
from PIL import Image
from sklearn.neighbors import NearestNeighbors
from torch.utils.data import DataLoader
from torch.utils.data import Dataset

from model.Birdview.dataset import make_images_info
from scipy.spatial.transform import Rotation as R
import torchvision.transforms.functional as TF


def pts_from_pixel_to_meter(pts_in_pixels, meters_per_pixel):
    pts_in_meters = pts_in_pixels[:,[1,0]] * meters_per_pixel - 50
    return pts_in_meters


def pts_from_meter_to_pixel(pts_in_meters, meters_per_pixel):
    pts_in_pixels = (pts_in_meters[:,[1,0]] + 50) / meters_per_pixel
    return pts_in_pixels


class MyRotation:
    """Rotate by one of the given angles."""
    def __init__(self, angle):
        self.angle = angle

    def __call__(self, x):
        return TF.rotate(x, self.angle)


def input_transforms(meters_per_pixel, rot_degree=None):
    if rot_degree is None:
        return transforms.Compose([
            transforms.Resize(size=(int(100 / meters_per_pixel), int(100 / meters_per_pixel))),
            # transforms.RandomRotation(degrees=360),
            transforms.ToTensor(),
        ])
    else:
        return transforms.Compose([
            transforms.Resize(size=(int(100/meters_per_pixel), int(100/meters_per_pixel))),
            # transforms.RandomRotation(degrees=360),
            MyRotation(rot_degree),
            transforms.ToTensor(),
        ])



class SuperglueDataset(Dataset):
    def __init__(self, images_info, images_dir, positive_search_radius, meters_per_pixel, add_rotation=False, return_filename=False):
        super(SuperglueDataset, self).__init__()
        self.meters_per_pixel = meters_per_pixel
        self.images_info = images_info
        self.images_dir = images_dir
        self.meters_per_pixel = meters_per_pixel
        self.add_rotation = add_rotation
        self.return_filename = return_filename

        self.for_database = False

        self.images_info = np.array(self.images_info)
        self._generate_train_dataset(positive_search_radius)

    # TODO: Determine (query, positive, negative) indices before feeding data
    def _generate_train_dataset(self, positive_search_radius):
        knn = NearestNeighbors()
        image_positions = np.array([image_info['position'] for image_info in self.images_info])
        knn.fit(image_positions)
        list_of_distances, self.list_of_tmp_positives_indices = knn.radius_neighbors(image_positions,
                                                                                     radius=positive_search_radius,
                                                                                     sort_results=True)
        self.list_of_positives_indices = []

        query_index = 0
        # max_angle_diff_in_radian = max_angle_diff_in_degree / 180 * np.pi
        i = 0
        for distances, positive_indices in zip(list_of_distances, self.list_of_tmp_positives_indices):
            # assert len(tmp_positive_indices) > 1
            # print(self.images_info[i]["image_file"])

            # tmp_positive_indices = tmp_positive_indices[1:]  # indices[0] is the query sample, remove it

            # positive_indices = tmp_positive_indices
            i += 1

            assert len(positive_indices) >= 2
            # probabilities = np.array(probabilities)
            # probabilities /= probabilities.sum()
            # self.list_of_positives_indices.append(
            #     np.random.choice(positive_indices, 1, replace=True))
            self.list_of_positives_indices.append(positive_indices[1:])
            query_index += 1

    @staticmethod
    def _make_se3(translation, orientation):
        tf = np.hstack([R.from_quat(orientation[[1, 2, 3, 0]]).as_matrix(),
                                translation.reshape(3, 1)])
        tf = np.vstack([tf, np.array([0, 0, 0, 1])])
        return tf

    def __len__(self):
        return len(self.images_info)

    def __getitem__(self, index):
        # query, query image, W * H
        # positive: positive image, W * H
        # T_query_positive: SE3 transform, 4 * 4, unit=meters
        query = Image.open(os.path.join(self.images_dir, self.images_info[index]['image_file']))
        pos_indices = self.list_of_positives_indices[index]
        pos_index = np.random.choice(pos_indices, 1, replace=True)[0]
        positive = Image.open(os.path.join(self.images_dir, self.images_info[pos_index]['image_file']))

        theta_in_deg = np.random.rand() * 360 if self.add_rotation else 0
        query = input_transforms(self.meters_per_pixel)(query)
        positive = input_transforms(self.meters_per_pixel, theta_in_deg)(positive)

        def T_rot_wrt_z(theta):
            return np.array([[np.cos(theta), np.sin(theta), 0, 0],
                             [-np.sin(theta), np.cos(theta), 0, 0],
                             [0,0,1,0],
                             [0,0,0,1]])

        # TODO: change T_query_positive
        T_w_query = self._make_se3(self.images_info[index]['position'], self.images_info[index]['orientation'])
        T_w_positive = self._make_se3(self.images_info[pos_index]['position'], self.images_info[pos_index]['orientation'])
        T_query_positive = np.linalg.inv(T_w_query) @ T_w_positive @ T_rot_wrt_z(theta_in_deg / 180 * np.pi)

        # convert translation in pixels
        # T_query_positive[:3,3] = T_query_positive[:3,3] / self.meters_per_pixel
        if self.return_filename:
            return query, positive, T_query_positive, \
                   os.path.join(self.images_dir, self.images_info[index]['image_file']), \
                   os.path.join(self.images_dir, self.images_info[pos_index]['image_file'])
        else:
            return query, positive, T_query_positive


if __name__ == '__main__':
    # dataset_dir = '/media/admini/My_data/0904/dataset'
    dataset_dir = '/media/admini/lavie/dataset/birdview_dataset'
    sequence = '00'
    positive_search_radius = 8
    images_info = make_images_info(
        struct_filename=os.path.join(dataset_dir, 'struct_file_' + sequence + '.txt'))
    images_dir = os.path.join(dataset_dir, sequence)
    dataset = SuperglueDataset(images_info=images_info, images_dir=images_dir,
                               positive_search_radius=positive_search_radius)
    data_loader = DataLoader(dataset, batch_size=2, shuffle=True)
    # with tqdm(data_loader) as tq:
    for item in data_loader:
        print(item)
    print(len(dataset))