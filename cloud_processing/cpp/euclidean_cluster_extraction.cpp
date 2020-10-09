#include <pcl/ModelCoefficients.h>
#include <pcl/point_types.h>
#include <pcl/io/pcd_io.h>
#include <pcl/filters/extract_indices.h>
#include <pcl/filters/voxel_grid.h>
#include <pcl/features/normal_3d.h>
#include <pcl/kdtree/kdtree.h>
#include <pcl/sample_consensus/method_types.h>
#include <pcl/sample_consensus/model_types.h>
#include <pcl/segmentation/sac_segmentation.h>
#include <pcl/segmentation/extract_clusters.h>

int main(int argc, char **argv)
{
    if (argc != 2) {
        std::cout << "usage: ./euclidean_cluster_extraction your-pcd-file\n";

        return 0;
    }
    
    // Read in the cloud data
    pcl::PCDReader reader;
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZ>), cloud_f(new pcl::PointCloud<pcl::PointXYZ>);
    reader.read(argv[1], *cloud);
    std::cout << "PointCloud before filtering has: " << cloud->points.size() << " data points." << std::endl; //*

    // Create the filtering object: downsample the dataset using a leaf size of 1cm
    pcl::VoxelGrid<pcl::PointXYZ> vg;
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_filtered(new pcl::PointCloud<pcl::PointXYZ>);
    vg.setInputCloud(cloud);
    vg.setLeafSize(0.1f, 0.1f, 0.1f);
    vg.filter(*cloud_filtered);

    *cloud_filtered = *cloud;
    std::cout << "PointCloud after filtering has: " << cloud_filtered->points.size() << " data points." << std::endl; //*

    // Create the segmentation object for the planar model and set all the parameters
    pcl::SACSegmentation<pcl::PointXYZ> seg;
    pcl::PointIndices::Ptr inliers(new pcl::PointIndices);
    pcl::ModelCoefficients::Ptr coefficients(new pcl::ModelCoefficients);
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_plane(new pcl::PointCloud<pcl::PointXYZ>());
    pcl::PCDWriter writer;
    seg.setOptimizeCoefficients(true);
    seg.setModelType(pcl::SACMODEL_PLANE);
    seg.setMethodType(pcl::SAC_RANSAC);
    seg.setMaxIterations(200);
    seg.setDistanceThreshold(0.5);

    // int nr_points = (int) cloud_filtered->points.size ();
    // while (cloud_filtered->points.size () > 0.5 * nr_points)
    // {
    //   // Segment the largest planar component from the remaining cloud
    //   seg.setInputCloud (cloud_filtered);
    //   seg.segment (*inliers, *coefficients);
    //   if (inliers->indices.size () == 0)
    //   {
    //       std::cout << "Could not estimate a planar model for the given dataset." << std::endl;
    //       break;
    //   }
    //   std::cout << "coef: " << *coefficients << std::endl;

    //   // Extract the planar inliers from the input cloud
    //   pcl::ExtractIndices<pcl::PointXYZ> extract;
    //   extract.setInputCloud (cloud_filtered);
    //   extract.setIndices (inliers);
    //   extract.setNegative (false);

    //   // Get the points associated with the planar surface
    //   extract.filter (*cloud_plane);
    //   std::cout << "PointCloud representing the planar component: " << cloud_plane->points.size () << " data points." << std::endl;

    //   // Remove the planar inliers, extract the rest
    //   extract.setNegative (true);
    //   extract.filter (*cloud_f);
    //   *cloud_filtered = *cloud_f;
    // }

    // Creating the KdTree object for the search method of the extraction
    pcl::search::KdTree<pcl::PointXYZ>::Ptr tree(new pcl::search::KdTree<pcl::PointXYZ>);
    tree->setInputCloud(cloud_filtered);

    std::vector<pcl::PointIndices> cluster_indices;
    pcl::EuclideanClusterExtraction<pcl::PointXYZ> ec;

    ec.setClusterTolerance(0.5);
    ec.setMinClusterSize(100);
    // ec.setMaxClusterSize (25000);
    ec.setSearchMethod(tree);
    ec.setInputCloud(cloud_filtered);
    ec.extract(cluster_indices);

    int j = 0;
    for (std::vector<pcl::PointIndices>::const_iterator it = cluster_indices.begin(); it != cluster_indices.end(); ++it)
    {
        if (it->indices.size() > 5000)
            continue;
        int r = rand() % 192 + 64;
        int g = rand() % 192 + 64;
        int b = rand() % 192 + 64;
        pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud_cluster(new pcl::PointCloud<pcl::PointXYZRGB>);
        for (std::vector<int>::const_iterator pit = it->indices.begin(); pit != it->indices.end(); ++pit)
        {
            pcl::PointXYZRGB point_rgb(r, g, b);
            point_rgb.x = cloud_filtered->points[*pit].x;
            point_rgb.y = cloud_filtered->points[*pit].y;
            point_rgb.z = cloud_filtered->points[*pit].z;
            cloud_cluster->points.push_back(point_rgb); //*
        }

        // if (cloud_cluster->points.size() > 1000) {
        //   tree->setInputCloud (cloud_cluster);
        //   ec.setClusterTolerance (0.2);
        //   ec.setMinClusterSize (100);
        //   // ec.setMaxClusterSize (25000);
        //   ec.setSearchMethod (tree);
        //   ec.setInputCloud (cloud_cluster);
        //   ec.extract (cluster_indices);
        // }

        cloud_cluster->width = cloud_cluster->points.size();
        cloud_cluster->height = 1;
        cloud_cluster->is_dense = true;

        std::cout << "PointCloud representing the Cluster: " << cloud_cluster->points.size() << " data points." << std::endl;
        std::stringstream ss;
        ss << "cloud_cluster_" << j << ".pcd";
        writer.write<pcl::PointXYZRGB>(ss.str(), *cloud_cluster, false); //*
        j++;
    }

    return (0);
}